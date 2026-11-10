from django.shortcuts import get_object_or_404, redirect, render
from django import forms
from django.contrib import messages
from django.db import transaction
from django.db.models.deletion import ProtectedError
from django.views.decorators.http import require_POST

from accounts.decorators import admin_required
from personnel.forms import PersonnelGroupForm
from personnel.models import PersonnelGroup


@admin_required
@require_POST
def group_bulk_delete(request):
    field = forms.ModelMultipleChoiceField(queryset=PersonnelGroup.objects.all())
    try:
        groups = list(field.clean(request.POST.getlist("groups")))
    except forms.ValidationError:
        messages.error(request, "请选择有效的分组后再删除")
        return redirect("personnel:group-list")
    deleted = 0
    protected = []
    for group in groups:
        try:
            with transaction.atomic():
                group.delete()
            deleted += 1
        except ProtectedError:
            protected.append(group.name)
    if deleted:
        messages.success(request, f"已删除 {deleted} 个分组，组员账号不受影响")
    if protected:
        messages.warning(request, "以下分组有关联抽样任务，已保留：" + "、".join(protected))
    return redirect("personnel:group-list")


@admin_required
def group_list(request):
    groups = PersonnelGroup.objects.prefetch_related("members").order_by("name")
    return render(request, "management/groups/list.html", {"groups": groups, "form": PersonnelGroupForm()})


@admin_required
def group_create(request):
    form = PersonnelGroupForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        group = form.save(commit=False)
        group.created_by = request.user
        group.save()
        form.save_m2m()
        return redirect("personnel:group-list")
    return render(request, "management/groups/list.html", {"form": form, "groups": PersonnelGroup.objects.prefetch_related("members").order_by("name"), "open_group_dialog": True})


@admin_required
def group_edit(request, pk):
    group = get_object_or_404(PersonnelGroup, pk=pk)
    form = PersonnelGroupForm(request.POST or None, instance=group)
    if request.method == "POST" and form.is_valid():
        form.save()
        return redirect("personnel:group-list")
    return render(
        request, "management/groups/list.html", {
            "form": form, "editing_group": group, "open_group_dialog": True,
            "groups": PersonnelGroup.objects.prefetch_related("members").order_by("name"),
        }
    )
