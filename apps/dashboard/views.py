from datetime import date

from rest_framework.response import Response
from rest_framework.views import APIView

from apps.jobs.models import Job, JobProduct
from apps.plans.models import JobProgress, SavedPlan
from apps.staff.models import Staff

OPEN_STATUSES = ('pending', 'scheduled', 'rescheduled')
DONE_STATUSES = ('completed', 'skip')


class DashboardView(APIView):
    """Single aggregated endpoint backing the Dashboard page.

    Replaces separate jobs/plans/staff/products fetches with server-side
    filtering + aggregation, driven by query params: date_from, date_to.
    """

    def get(self, request):
        params = request.query_params
        date_from = params.get('date_from') or None
        date_to = params.get('date_to') or None

        jobs = Job.objects.all()
        if date_from:
            jobs = jobs.filter(service_date__gte=date_from)
        if date_to:
            jobs = jobs.filter(service_date__lte=date_to)
        jobs = list(jobs)

        completions = [j for j in jobs if j.status in DONE_STATUSES]
        completion_lines = list(
            JobProduct.objects.filter(job__in=completions).select_related('product')
        )

        plans = SavedPlan.objects.all()
        if date_from:
            plans = plans.filter(plan_date__gte=date_from)
        if date_to:
            plans = plans.filter(plan_date__lte=date_to)
        plans = list(plans)

        staff = list(Staff.objects.all())

        today = date.today()

        by_status: dict = {}
        overdue = 0
        due_7 = 0
        pipeline_value = 0
        for j in jobs:
            by_status[j.status] = by_status.get(j.status, 0) + 1
            if j.status != 'completed':
                days = (j.service_date - today).days
                if days < 0:
                    overdue += 1
                elif days <= 7:
                    due_7 += 1
            if j.status in OPEN_STATUSES:
                pipeline_value += float(j.service_value or 0)

        service_revenue = sum(float(j.service_value or 0) for j in completions)
        installs_completed = sum(1 for j in completions if j.service_type == 'installation')

        product_totals: dict = {}
        sales_revenue = 0.0
        for line in completion_lines:
            pid = str(line.product_id)
            qty = float(line.quantity)
            price = float(line.unit_price)
            total = qty * price
            sales_revenue += total
            entry = product_totals.setdefault(pid, {'qty': 0.0, 'revenue': 0.0, 'name': line.product.name})
            entry['qty'] += qty
            entry['revenue'] += total

        top_product_entries = sorted(product_totals.items(), key=lambda kv: kv[1]['revenue'], reverse=True)[:8]
        top_products = [
            {
                'product_id': pid,
                'product_name': totals['name'],
                'qty': totals['qty'],
                'revenue': totals['revenue'],
            }
            for pid, totals in top_product_entries
        ]

        total_km = sum(float(p.road_km or 0) for p in plans)

        upcoming_jobs = sorted(
            (j for j in jobs if j.service_date >= today and j.status in OPEN_STATUSES),
            key=lambda j: (j.service_date, j.service_time),
        )[:8]

        recent_completions = sorted(completions, key=lambda j: j.updated_at, reverse=True)[:8]

        return Response({
            'stats': {
                'total_jobs': len(jobs),
                'by_status': by_status,
                'overdue': overdue,
                'due_7': due_7,
                'service_revenue': service_revenue,
                'sales_revenue': sales_revenue,
                'total_revenue': service_revenue + sales_revenue,
                'pipeline_value': pipeline_value,
                'total_km': total_km,
                'active_staff': sum(1 for s in staff if s.active),
                'total_staff': len(staff),
                'plans_count': len(plans),
                'installs_completed': installs_completed,
                'completions_count': len(completions),
            },
            'top_products': top_products,
            'upcoming_jobs': [
                {
                    'id': str(j.id),
                    'name': j.name,
                    'address': j.address,
                    'service_date': j.service_date.isoformat(),
                    'service_time': j.service_time.isoformat() if j.service_time else None,
                }
                for j in upcoming_jobs
            ],
            'recent_completions': [
                {
                    'id': str(j.id),
                    'name': j.name,
                    'service_date': j.service_date.isoformat(),
                    'service_value': float(j.service_value or 0),
                }
                for j in recent_completions
            ],
        })


def _build_staff_report(staff_id: str, date_from: str | None, date_to: str | None) -> dict:
    """Core aggregation shared by StaffReportView (one staff, full detail)
    and StaffReportSummaryView (all staff, totals only)."""

    jobs_qs = Job.objects.filter(job_staff__staff_id=staff_id)
    if date_from:
        jobs_qs = jobs_qs.filter(service_date__gte=date_from)
    if date_to:
        jobs_qs = jobs_qs.filter(service_date__lte=date_to)
    staff_jobs = list(jobs_qs)

    plans_qs = SavedPlan.objects.filter(staff_ids__contains=[staff_id])
    if date_from:
        plans_qs = plans_qs.filter(plan_date__gte=date_from)
    if date_to:
        plans_qs = plans_qs.filter(plan_date__lte=date_to)
    plans = list(plans_qs)
    plan_ids = [p.id for p in plans]

    progress = list(JobProgress.objects.filter(staff_id=staff_id, plan_id__in=plan_ids))

    actual_km_by_job: dict = {}
    actual_time_by_job: dict = {}
    completed_job_ids = set()
    for pr in progress:
        jid = str(pr.job_id)
        if pr.actual_km is not None:
            actual_km_by_job[jid] = actual_km_by_job.get(jid, 0) + float(pr.actual_km)
        if pr.status == 'completed':
            completed_job_ids.add(jid)
            actual_time_by_job[jid] = pr.updated_at.isoformat()

    # Jobs referenced by plans/progress may fall outside the staff-jobs
    # set above (e.g. different service_date) — fetch those too so plan
    # completed-value and revenue totals can resolve service_value/status.
    referenced_ids = set(completed_job_ids)
    for p in plans:
        referenced_ids.update(str(jid) for jid in (p.ordered_job_ids or []))
    lookup_jobs = {str(j.id): j for j in staff_jobs}
    missing_ids = referenced_ids - set(lookup_jobs)
    if missing_ids:
        for j in Job.objects.filter(id__in=missing_ids):
            lookup_jobs[str(j.id)] = j

    by_status: dict = {}
    for j in staff_jobs:
        by_status[j.status] = by_status.get(j.status, 0) + 1

    allocated_km = sum(float(p.road_km or 0) for p in plans)
    allocated_min = sum(int(p.road_minutes or 0) for p in plans)
    actual_km_total = sum(actual_km_by_job.values())

    completed_ids = {str(j.id) for j in staff_jobs if j.status == 'completed'} | completed_job_ids
    service_revenue = 0.0
    service_count = 0
    install_revenue = 0.0
    install_count = 0
    for jid in completed_ids:
        j = lookup_jobs.get(jid)
        if not j:
            continue
        val = float(j.service_value or 0)
        if j.service_type == 'installation':
            install_revenue += val
            install_count += 1
        else:
            service_revenue += val
            service_count += 1

    job_travel: dict = {}
    plan_rows = []
    for p in plans:
        ordered = [str(jid) for jid in (p.ordered_job_ids or [])]
        legs = p.legs or []
        value = 0.0
        count = 0
        for i, jid in enumerate(ordered):
            leg = legs[i] if i < len(legs) else None
            if leg:
                entry = job_travel.setdefault(jid, {'km': 0.0, 'min': 0.0, 'visits': 0})
                entry['km'] += float(leg.get('distanceKm') or 0)
                entry['min'] += float(leg.get('minutes') or 0)
                entry['visits'] += 1
            j = lookup_jobs.get(jid)
            if j and (jid in completed_job_ids or j.status == 'completed'):
                value += float(j.service_value or 0)
                count += 1
        plan_rows.append({
            'id': str(p.id),
            'plan_date': p.plan_date.isoformat(),
            'name': p.name,
            'base_name': p.base_name,
            'stops': len(ordered),
            'road_km': float(p.road_km) if p.road_km is not None else None,
            'road_minutes': p.road_minutes,
            'completed_value': value,
            'completed_count': count,
        })

    job_rows = []
    for j in sorted(staff_jobs, key=lambda j: (j.service_date, j.service_time)):
        jid = str(j.id)
        t = job_travel.get(jid)
        job_rows.append({
            'id': jid,
            'service_date': j.service_date.isoformat(),
            'service_time': j.service_time.isoformat() if j.service_time else None,
            'name': j.name,
            'address': j.address,
            'service_type': j.service_type,
            'status': j.status,
            'service_value': float(j.service_value or 0),
            'actual_time': actual_time_by_job.get(jid),
            'travel_km': t['km'] if t else None,
            'travel_min': t['min'] if t else None,
            'actual_km': actual_km_by_job.get(jid),
            'is_completed': jid in completed_ids,
        })

    return {
        'plans': plan_rows,
        'jobs': job_rows,
        'totals': {
            'plans_count': len(plans),
            'jobs_count': len(staff_jobs),
            'completed_count': by_status.get('completed', 0),
            'allocated_km': allocated_km,
            'allocated_min': allocated_min,
            'actual_km': actual_km_total,
            'service_revenue': service_revenue,
            'service_count': service_count,
            'install_revenue': install_revenue,
            'install_count': install_count,
        },
    }


class StaffReportView(APIView):
    """Single aggregated endpoint backing the Staff Reports page.

    Replaces separate jobs/plans/job-staff/job-progress fetches (previously
    pulled in full and filtered client-side) with one query scoped to a
    single staff member and date range: staff_id (required), date_from,
    date_to.
    """

    def get(self, request):
        staff_id = request.query_params.get('staff_id')
        if not staff_id:
            return Response({'detail': 'staff_id is required.'}, status=400)

        date_from = request.query_params.get('date_from') or None
        date_to = request.query_params.get('date_to') or None

        return Response(_build_staff_report(staff_id, date_from, date_to))


class StaffReportSummaryView(APIView):
    """All-staff summary for the Staff Reports page: one totals row per staff
    member for the given date range, reusing the same per-staff aggregation
    as StaffReportView so the numbers always match on drill-down."""

    def get(self, request):
        date_from = request.query_params.get('date_from') or None
        date_to = request.query_params.get('date_to') or None

        staff = list(Staff.objects.all())
        rows = []
        for s in staff:
            totals = _build_staff_report(str(s.id), date_from, date_to)['totals']
            rows.append({
                'id': str(s.id),
                'name': s.name,
                'active': s.active,
                'total_revenue': totals['service_revenue'] + totals['install_revenue'],
                **totals,
            })

        rows.sort(key=lambda r: r['total_revenue'], reverse=True)
        return Response({'staff': rows})
