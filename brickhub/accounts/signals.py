from django.contrib.auth.signals import user_logged_in
from django.dispatch import receiver


@receiver(user_logged_in)
def merge_guest_data(sender, request, user, **kwargs):
    if request is None:
        return
    from cart.services import merge_session_into_user

    merge_session_into_user(request, user)
