from django.contrib.auth import get_user_model
from django.contrib.auth.backends import ModelBackend


class EmailBackend(ModelBackend):
    """Authenticate with a case-insensitive e-mail address."""

    def authenticate(self, request, username=None, password=None, email=None, **kwargs):
        login = (email or username or kwargs.get(get_user_model().USERNAME_FIELD) or "").strip()
        if not login or password is None:
            return None
        User = get_user_model()
        try:
            user = User.objects.get(email__iexact=login)
        except User.DoesNotExist:
            # Run the hasher anyway to reduce timing differences.
            User().set_password(password)
            return None
        if user.check_password(password) and self.user_can_authenticate(user):
            return user
        return None
