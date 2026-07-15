import logging

from django.http import HttpResponseRedirect
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_exempt
from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView
from django.conf import settings

from .oauth import (
    build_authorize_url,
    exchange_code,
    get_install_config,
    get_token_status,
    refresh_company_token,
    sync_location_contacts,
    update_contact_custom_field,
)
from .serializers import ExchangeCodeSerializer, UpdateContactCustomFieldSerializer

logger = logging.getLogger(__name__)


class GhlAuthorizeView(APIView):
    """Redirect the browser to the GHL OAuth consent page."""
    permission_classes = [AllowAny]

    def get(self, _request):
        return HttpResponseRedirect(build_authorize_url())


class GhlCallbackView(APIView): 
    """Handle the OAuth callback from GHL, exchange the code, redirect back to frontend."""
    permission_classes = [AllowAny]

    def get(self, request):
        frontend = settings.GHL_FRONTEND_URL.rstrip('/')
        code = request.GET.get('code')
        error = request.GET.get('error')

        if error or not code:
            msg = error or 'missing_code'
            return HttpResponseRedirect(f'{frontend}/connect?ghl=error&msg={msg}')

        try:
            exchange_code(code, settings.GHL_REDIRECT_URI)
        except Exception as exc:
            logger.error('GHL callback exchange failed: %s', exc)
            from urllib.parse import quote
            return HttpResponseRedirect(
                f'{frontend}/connect?ghl=error&msg={quote(str(exc), safe="")}'
            )

        # Best-effort contact sync — don't fail the OAuth flow if this errors
        try:
            count = sync_location_contacts()
            logger.info('Post-OAuth contact sync: %d contacts', count)
        except Exception as exc:
            logger.warning('Post-OAuth contact sync failed (non-fatal): %s', exc)

        return HttpResponseRedirect(f'{frontend}/connect?ghl=success')


class GhlConfigView(APIView):
    def get(self, request):
        return Response(get_install_config())


class GhlStatusView(APIView):
    def get(self, request):
        return Response(get_token_status())


class GhlExchangeView(APIView):
    def post(self, request):
        serializer = ExchangeCodeSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            exchange_code(
                code=serializer.validated_data['code'],
                redirect_uri=serializer.validated_data['redirect_uri'],
            )
            return Response({'success': True})
        except Exception as exc:
            logger.error('GHL exchange failed: %s', exc)
            return Response({'detail': str(exc)}, status=status.HTTP_400_BAD_REQUEST)


class GhlRefreshView(APIView):
    def post(self, request):
        try:
            refresh_company_token()
            return Response({'success': True})
        except Exception as exc:
            logger.error('GHL refresh failed: %s', exc)
            return Response({'detail': str(exc)}, status=status.HTTP_400_BAD_REQUEST)


class GhlSyncContactsView(APIView):
    def post(self, request):
        try:
            count = sync_location_contacts()
            return Response({'synced': count})
        except Exception as exc:
            logger.error('GHL contact sync failed: %s', exc)
            return Response({'detail': str(exc)}, status=status.HTTP_400_BAD_REQUEST)


@method_decorator(csrf_exempt, name='dispatch')
class GhlUpdateContactView(APIView):
    """Open webhook endpoint called by GHL workflows to update a contact's name custom field."""
    permission_classes = [AllowAny]
    authentication_classes = []

    def post(self, request):
        serializer = UpdateContactCustomFieldSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            result = update_contact_custom_field(
                contact_id=serializer.validated_data['contact_id'],
                name_value=serializer.validated_data['customData']['name'],
            )
            return Response({'success': True, 'contact': result})
        except Exception as exc:
            logger.error('GHL contact update failed: %s', exc)
            return Response({'detail': str(exc)}, status=status.HTTP_400_BAD_REQUEST)
