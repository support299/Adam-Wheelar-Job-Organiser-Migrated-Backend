from django.conf import settings
from django.contrib.auth import get_user_model
from rest_framework import status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.exceptions import TokenError
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.views import TokenObtainPairView

from .serializers import ChangePasswordSerializer, CustomTokenObtainPairSerializer, UserSerializer


class LoginView(TokenObtainPairView):
    serializer_class = CustomTokenObtainPairSerializer


class LogoutView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        refresh_token = request.data.get('refresh')
        if not refresh_token:
            return Response(
                {'detail': 'refresh token is required.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            token = RefreshToken(refresh_token)
            token.blacklist()
        except TokenError:
            return Response(
                {'detail': 'Token is invalid or already blacklisted.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        return Response(status=status.HTTP_204_NO_CONTENT)


class MeView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        return Response(UserSerializer(request.user).data)


class ChangePasswordView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = ChangePasswordSerializer(data=request.data, context={'request': request})
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response({'detail': 'Password updated successfully.'})


class IframeTokenView(APIView):
    """Issue a JWT silently for the GHL iframe embed.

    The caller must supply the shared secret configured in IFRAME_SECRET.
    Returns tokens for the user whose email matches IFRAME_USER_EMAIL.
    No password is required — the secret is the sole auth mechanism.
    """
    permission_classes = [AllowAny]

    def post(self, request):
        iframe_secret = getattr(settings, 'IFRAME_SECRET', '')
        if not iframe_secret:
            return Response({'detail': 'IFRAME_SECRET not configured.'}, status=status.HTTP_503_SERVICE_UNAVAILABLE)

        supplied = request.data.get('secret', '')
        if not supplied or supplied != iframe_secret:
            return Response({'detail': 'Invalid secret.'}, status=status.HTTP_401_UNAUTHORIZED)

        email = getattr(settings, 'IFRAME_USER_EMAIL', '')
        if not email:
            return Response({'detail': 'IFRAME_USER_EMAIL not configured.'}, status=status.HTTP_503_SERVICE_UNAVAILABLE)

        User = get_user_model()
        try:
            user = User.objects.get(email=email)
        except User.DoesNotExist:
            return Response({'detail': f'User {email} not found.'}, status=status.HTTP_503_SERVICE_UNAVAILABLE)

        refresh = RefreshToken.for_user(user)
        return Response({
            'access': str(refresh.access_token),
            'refresh': str(refresh),
        })
