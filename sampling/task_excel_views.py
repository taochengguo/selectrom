import time
from uuid import uuid4

from django import forms
from django.contrib import messages
from django.core.exceptions import ValidationError
from django.shortcuts import redirect, render
from django.http import JsonResponse
from django.urls import reverse
from django.views.decorators.http import require_http_methods

from accounts.decorators import admin_required
from personnel.models import PersonnelGroup
from sampling.services.task_excel import ExcelTaskForm, commit_rows, parse_task_workbook, prepare_rows


SESSION_KEY = 'task_excel_previews'


class UploadForm(forms.Form):
    file = forms.FileField(label='Excel 周计划', widget=forms.FileInput(attrs={'accept': '.xlsx'}))
    personnel_group = forms.ModelChoiceField(label='统一抽样人员分组', queryset=PersonnelGroup.objects.all(), empty_label='请选择抽样组')


@admin_required
@require_http_methods(['GET', 'POST'])
def task_excel_import(request):
    now = time.time()
    previews = {key: value for key, value in request.session.get(SESSION_KEY, {}).items()
                if value.get('owner') == request.user.pk and now - value.get('created_at', 0) < 3600}
    token = request.POST.get('token', '') if request.method == 'POST' else request.GET.get('token', '')
    error = ''
    upload_form = UploadForm()
    draft = previews.get(token)
    group = None
    rows = []
    if request.method == 'POST' and request.POST.get('action') == 'upload':
        upload_form = UploadForm(request.POST, request.FILES)
        if upload_form.is_valid():
            try:
                rows = parse_task_workbook(upload_form.cleaned_data['file'])
            except ValueError as exc:
                upload_form.add_error('file', str(exc))
            else:
                token = uuid4().hex
                # Bound session storage even when many tabs upload different files.
                while len(previews) >= 3:
                    del previews[next(iter(previews))]
                previews[token] = {'owner': request.user.pk, 'created_at': now, 'rows': rows,
                                   'group': upload_form.cleaned_data['personnel_group'].pk,
                                   'filename': upload_form.cleaned_data['file'].name}
                request.session[SESSION_KEY] = previews
                return redirect(f"{reverse('management:task-excel-import')}?token={token}")
    elif token and not draft:
        error = '预览已失效或已导入，请重新上传文件。'
    elif draft:
        group_id = request.POST.get('personnel_group') if request.method == 'POST' else draft['group']
        group = PersonnelGroup.objects.filter(pk=group_id).first() if str(group_id).isdigit() else None
        rows = draft['rows']
        if request.method == 'POST':
            fields = list(ExcelTaskForm().fields)
            rows = [{'row_number': row['row_number'], 'data': {
                field: request.POST.get(f'row-{index}-{field}', '') for field in fields}}
                for index, row in enumerate(rows) if not request.POST.get(f'row-{index}-delete')]
            draft['rows'] = rows
            draft['group'] = group.pk if group else None
            previews[token] = draft
            request.session[SESSION_KEY] = previews
            if not group:
                error = '请选择有效的抽样人员分组。'
            elif not rows:
                error = '请至少保留一条任务，或重新上传文件。'
            elif request.POST.get('action') == 'confirm':
                try:
                    created, skipped = commit_rows(rows, group, request.user)
                except (ValueError, ValidationError) as exc:
                    error = '；'.join(exc.messages) if isinstance(exc, ValidationError) else str(exc)
                else:
                    del previews[token]
                    request.session[SESSION_KEY] = previews
                    messages.success(request, f'Excel 导入完成：创建 {len(created)} 个草稿任务，跳过 {skipped} 条完全重复记录。')
                    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                        return JsonResponse({'redirect': reverse('management:task-list')})
                    return redirect('management:task-list')
    prepared = prepare_rows(rows, group) if draft else []
    invalid_count = sum(not row['form'].is_valid() for row in prepared)
    duplicate_count = sum(row['duplicate'] for row in prepared)
    template = 'management/tasks/_excel_import_content.html' if request.headers.get('X-Requested-With') == 'XMLHttpRequest' else 'management/tasks/excel_import.html'
    return render(request, template, {
        'upload_form': upload_form, 'token': token if draft else '', 'rows': prepared,
        'groups': PersonnelGroup.objects.order_by('name'), 'group': group,
        'filename': draft['filename'] if draft else '', 'error': error,
        'invalid_count': invalid_count, 'duplicate_count': duplicate_count,
        'new_count': len(prepared) - invalid_count - duplicate_count,
        'can_confirm': bool(prepared) and bool(group) and not invalid_count,
    })
