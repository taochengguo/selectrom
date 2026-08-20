from django.shortcuts import get_object_or_404, redirect, render

from accounts.decorators import admin_required
from personnel.forms import PersonnelGroupForm
from personnel.models import PersonnelGroup


@admin_required
def group_list(request):
    groups = PersonnelGroup.objects.prefetch_related("members").order_by("name")
    return render(request, "management/groups/list.html", {"groups": groups})


@admin_required
def group_create(request):
    form = PersonnelGroupForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        group = form.save(commit=False)
        group.created_by = request.user
        group.save()
        form.save_m2m()
        return redirect("personnel:group-list")
    return render(request, "management/groups/form.html", {"form": form})


@admin_required
def group_edit(request, pk):
    group = get_object_or_404(PersonnelGroup, pk=pk)
    form = PersonnelGroupForm(request.POST or None, instance=group)
    if request.method == "POST" and form.is_valid():
        form.save()
        return redirect("personnel:group-list")
    return render(
        request, "management/groups/form.html", {"form": form, "group": group}
    )
