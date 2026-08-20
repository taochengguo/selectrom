from functools import wraps

from django.core.exceptions import PermissionDenied
from django.shortcuts import redirect

from accounts.models import User


def role_required(role):
    def decorator(view):
        @wraps(view)
        def wrapped(request, *args, **kwargs):
            if not request.user.is_authenticated:
                return redirect("accounts:login")
            if request.user.role != role:
                raise PermissionDenied
            return view(request, *args, **kwargs)

        return wrapped

    return decorator


admin_required = role_required(User.Role.ADMIN)
sampler_required = role_required(User.Role.SAMPLER)
