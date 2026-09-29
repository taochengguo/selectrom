from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client, TestCase
from django.urls import reverse

from accounts.models import User
from audit.models import TaskAuditLog
from personnel.models import PersonnelGroup
from sampling.models import (
    CandidateMaterial,
    PersonnelAssignment,
    SamplingBatch,
    SamplingResult,
    SamplingTask,
)
from sampling.services.drawing import draw_materials


class ManagementViewTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_user("admin", role=User.Role.ADMIN)
        self.sampler = User.objects.create_user("sampler", role=User.Role.SAMPLER)
        self.other_sampler = User.objects.create_user("sampler2", role=User.Role.SAMPLER)
        self.group = PersonnelGroup.objects.create(name="第一组", created_by=self.admin)
        self.group.members.add(self.sampler, self.other_sampler)
        self.client.force_login(self.admin)

    def make_task(self, *, number="T-1", status=SamplingTask.Status.DRAFT, count=1):
        return SamplingTask.objects.create(
            task_number=number,
            name="测试任务",
            personnel_group=self.group,
            draw_count=count,
            status=status,
            created_by=self.admin,
        )

    def add_candidate(self, task, number="M-1"):
        return CandidateMaterial.objects.create(
            task=task,
            material_number=number,
            order_number="O-1",
            supplier="供应商",
            material_name="物资",
            quantity=10,
        )

    def test_sampler_cannot_execute_task_endpoint(self):
        self.client.force_login(self.sampler)

        response = self.client.post(reverse("management:task-execute", args=[1]))

        self.assertEqual(response.status_code, 403)

    def test_execute_endpoint_rejects_get(self):
        response = self.client.get(reverse("management:task-execute", args=[1]))

        self.assertEqual(response.status_code, 405)

    def test_admin_creates_and_edits_task_through_lifecycle(self):
        response = self.client.post(
            reverse("management:task-create"),
            {
                "task_number": "T-100",
                "name": "首次任务",
                "personnel_group": self.group.pk,
                "draw_count": 1,
                "notes": "初始备注",
            },
        )
        task = SamplingTask.objects.get(task_number="T-100")
        self.assertRedirects(response, reverse("management:task-detail", args=[task.pk]))
        self.assertTrue(TaskAuditLog.objects.filter(task=task, event_type="task.created").exists())

        response = self.client.post(
            reverse("management:task-edit", args=[task.pk]),
            {
                "task_number": "T-100",
                "name": "修改后的任务",
                "personnel_group": self.group.pk,
                "draw_count": 1,
                "notes": "已修改",
            },
        )
        task.refresh_from_db()
        self.assertRedirects(response, reverse("management:task-detail", args=[task.pk]))
        self.assertEqual(task.name, "修改后的任务")
        self.assertTrue(TaskAuditLog.objects.filter(task=task, event_type="task.updated").exists())

    def test_executed_task_edit_sends_only_changed_nonprotected_fields(self):
        for index, status in enumerate(
            (SamplingTask.Status.ASSIGNED, SamplingTask.Status.IN_PROGRESS), start=1
        ):
            with self.subTest(status=status):
                task = self.make_task(number=f"EDIT-{index}", status=status)

                response = self.client.post(
                    reverse("management:task-edit", args=[task.pk]),
                    {
                        "task_number": task.task_number,
                        "name": f"修改名称-{index}",
                        "personnel_group": self.group.pk,
                        "draw_count": task.draw_count,
                        "notes": f"修改备注-{index}",
                    },
                )

                self.assertRedirects(
                    response, reverse("management:task-detail", args=[task.pk])
                )
                task.refresh_from_db()
                self.assertEqual(task.name, f"修改名称-{index}")
                self.assertEqual(task.notes, f"修改备注-{index}")

    def test_executed_task_edit_still_rejects_protected_field_changes(self):
        other_group = PersonnelGroup.objects.create(name="第二组", created_by=self.admin)
        task = self.make_task(status=SamplingTask.Status.ASSIGNED)

        response = self.client.post(
            reverse("management:task-edit", args=[task.pk]),
            {
                "task_number": task.task_number,
                "name": task.name,
                "personnel_group": other_group.pk,
                "draw_count": 2,
                "notes": task.notes,
            },
        )

        self.assertEqual(response.status_code, 200)
        task.refresh_from_db()
        self.assertEqual(task.personnel_group, self.group)
        self.assertEqual(task.draw_count, 1)
        self.assertContains(response, "任务已执行，抽样组和抽取数量不可修改")

    def test_admin_adds_and_deletes_candidate_through_lifecycle(self):
        task = self.make_task()
        response = self.client.post(
            reverse("management:task-candidate-add", args=[task.pk]),
            {
                "material_number": "M-100",
                "order_number": "O-100",
                "supplier": "供应商甲",
                "material_name": "螺栓",
                "quantity": 20,
            },
        )
        candidate = CandidateMaterial.objects.get(task=task, material_number="M-100")
        self.assertRedirects(response, reverse("management:task-detail", args=[task.pk]))

        response = self.client.post(
            reverse("management:task-candidate-delete", args=[candidate.pk])
        )
        self.assertRedirects(response, reverse("management:task-detail", args=[task.pk]))
        self.assertFalse(CandidateMaterial.objects.filter(pk=candidate.pk).exists())
        self.assertTrue(TaskAuditLog.objects.filter(task=task, event_type="material.deleted").exists())

    def test_admin_edits_candidate_through_audited_lifecycle_service(self):
        task = self.make_task()
        candidate = self.add_candidate(task)

        detail = self.client.get(reverse("management:task-detail", args=[task.pk]))
        response = self.client.post(
            reverse("management:task-candidate-edit", args=[candidate.pk]),
            {
                "material_number": "M-EDITED",
                "order_number": "O-EDITED",
                "supplier": "new supplier",
                "material_name": "new material",
                "quantity": 25,
            },
        )

        self.assertContains(
            detail,
            reverse("management:task-candidate-edit", args=[candidate.pk]),
        )
        self.assertRedirects(response, reverse("management:task-detail", args=[task.pk]))
        candidate.refresh_from_db()
        self.assertEqual(candidate.material_number, "M-EDITED")
        self.assertEqual(candidate.quantity, 25)
        audit = TaskAuditLog.objects.get(task=task, event_type="material.updated")
        self.assertEqual(audit.before_data["material_number"], "M-1")
        self.assertEqual(audit.after_data["material_number"], "M-EDITED")

    def test_candidate_edit_keeps_submitted_values_and_errors_when_validation_fails(self):
        task = self.make_task()
        candidate = self.add_candidate(task)

        response = self.client.post(
            reverse("management:task-candidate-edit", args=[candidate.pk]),
            {
                "material_number": "M-EDITED",
                "order_number": "O-EDITED",
                "supplier": "new supplier",
                "material_name": "new material",
                "quantity": 0,
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context["form"].errors)
        self.assertContains(response, 'value="M-EDITED"')
        candidate.refresh_from_db()
        self.assertEqual(candidate.material_number, "M-1")
        self.assertEqual(candidate.quantity, 10)
        self.assertFalse(TaskAuditLog.objects.filter(event_type="material.updated").exists())

    def test_candidate_edit_reports_executed_task_freeze_without_changing_candidate(self):
        task = self.make_task(status=SamplingTask.Status.ASSIGNED)
        candidate = self.add_candidate(task)

        response = self.client.post(
            reverse("management:task-candidate-edit", args=[candidate.pk]),
            {
                "material_number": candidate.material_number,
                "order_number": candidate.order_number,
                "supplier": candidate.supplier,
                "material_name": "must not persist",
                "quantity": candidate.quantity,
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(
            response,
            "\u4efb\u52a1\u5df2\u6267\u884c\uff0c\u5019\u9009\u7269\u8d44\u4e0d\u53ef\u4fee\u6539",
        )
        candidate.refresh_from_db()
        self.assertEqual(candidate.material_name, "\u7269\u8d44")
        self.assertFalse(TaskAuditLog.objects.filter(event_type="material.updated").exists())

    def test_candidate_edit_is_administrator_only(self):
        task = self.make_task()
        candidate = self.add_candidate(task)
        self.client.force_login(self.sampler)
        url = reverse("management:task-candidate-edit", args=[candidate.pk])

        self.assertEqual(self.client.get(url).status_code, 403)
        self.assertEqual(
            self.client.post(
                url,
                {
                    "material_number": "M-EDITED",
                    "order_number": "O-EDITED",
                    "supplier": "new supplier",
                    "material_name": "new material",
                    "quantity": 25,
                },
            ).status_code,
            403,
        )

    def test_candidate_edit_post_requires_csrf(self):
        task = self.make_task()
        candidate = self.add_candidate(task)
        csrf_client = Client(enforce_csrf_checks=True)
        csrf_client.force_login(self.admin)

        response = csrf_client.post(
            reverse("management:task-candidate-edit", args=[candidate.pk]),
            {
                "material_number": "M-EDITED",
                "order_number": "O-EDITED",
                "supplier": "new supplier",
                "material_name": "new material",
                "quantity": 25,
            },
        )

        self.assertEqual(response.status_code, 403)
        candidate.refresh_from_db()
        self.assertEqual(candidate.material_number, "M-1")

    def test_admin_imports_csv_and_marks_task_ready(self):
        task = self.make_task()
        csv_file = SimpleUploadedFile(
            "materials.csv",
            "物资编号,订单号,供应商,物资名称,物资数量\nM-1,O-1,供应商甲,螺栓,10\n".encode("utf-8-sig"),
            content_type="text/csv",
        )

        response = self.client.post(
            reverse("management:task-import", args=[task.pk]), {"csv_file": csv_file}
        )
        self.assertRedirects(response, reverse("management:task-detail", args=[task.pk]))
        self.assertEqual(task.candidates.count(), 1)

        response = self.client.post(reverse("management:task-ready", args=[task.pk]))
        task.refresh_from_db()
        self.assertRedirects(response, reverse("management:task-detail", args=[task.pk]))
        self.assertEqual(task.status, SamplingTask.Status.READY)

    def test_execute_reassign_redraw_and_cancel_actions_preserve_history(self):
        task = self.make_task(status=SamplingTask.Status.READY)
        self.add_candidate(task)

        response = self.client.post(reverse("management:task-execute", args=[task.pk]))
        task.refresh_from_db()
        self.assertRedirects(response, reverse("management:task-detail", args=[task.pk]))
        self.assertEqual(task.status, SamplingTask.Status.ASSIGNED)
        first_assignment = task.personnel_assignments.get(kind=PersonnelAssignment.Kind.INITIAL)

        response = self.client.post(
            reverse("management:task-reassign", args=[task.pk]), {"reason": "原人员临时无法到场"}
        )
        task.refresh_from_db()
        self.assertRedirects(response, reverse("management:task-detail", args=[task.pk]))
        self.assertEqual(task.personnel_assignments.count(), 2)
        first_assignment.refresh_from_db()
        self.assertFalse(first_assignment.is_current)

        current_sampler = task.personnel_assignments.get(is_current=True).selected_user
        draw_materials(task_id=task.pk, actor=current_sampler)
        response = self.client.post(
            reverse("management:task-authorize-redraw", args=[task.pk]),
            {"reason": "样品损坏"},
        )
        task.refresh_from_db()
        self.assertRedirects(response, reverse("management:task-detail", args=[task.pk]))
        self.assertEqual(task.status, SamplingTask.Status.ASSIGNED)
        self.assertEqual(task.sampling_batches.count(), 2)
        self.assertTrue(
            task.sampling_batches.filter(
                kind=SamplingBatch.Kind.REDRAW, status=SamplingBatch.Status.AUTHORIZED
            ).exists()
        )

        response = self.client.post(reverse("management:task-cancel", args=[task.pk]))
        task.refresh_from_db()
        self.assertRedirects(response, reverse("management:task-detail", args=[task.pk]))
        self.assertEqual(task.status, SamplingTask.Status.CANCELLED)
        self.assertEqual(task.personnel_assignments.count(), 2)
        self.assertEqual(task.sampling_batches.count(), 2)

    def test_reassignment_requires_reason_and_does_not_change_history(self):
        task = self.make_task(status=SamplingTask.Status.ASSIGNED)
        PersonnelAssignment.objects.create(
            task=task,
            candidate_user_ids=[self.sampler.pk, self.other_sampler.pk],
            selected_user=self.sampler,
            kind=PersonnelAssignment.Kind.INITIAL,
            is_current=True,
            created_by=self.admin,
        )

        response = self.client.post(reverse("management:task-reassign", args=[task.pk]), {"reason": " "})

        self.assertRedirects(response, reverse("management:task-detail", args=[task.pk]))
        self.assertEqual(task.personnel_assignments.count(), 1)

    def test_all_state_changing_task_actions_are_post_only(self):
        task = self.make_task()
        candidate = self.add_candidate(task)
        urls = [
            reverse("management:task-ready", args=[task.pk]),
            reverse("management:task-execute", args=[task.pk]),
            reverse("management:task-reassign", args=[task.pk]),
            reverse("management:task-authorize-redraw", args=[task.pk]),
            reverse("management:task-cancel", args=[task.pk]),
            reverse("management:task-candidate-delete", args=[candidate.pk]),
        ]

        for url in urls:
            with self.subTest(url=url):
                self.assertEqual(self.client.get(url).status_code, 405)

    def test_detail_displays_material_assignment_batch_result_and_audit_history(self):
        task = self.make_task(status=SamplingTask.Status.ASSIGNED)
        material = self.add_candidate(task)
        PersonnelAssignment.objects.create(
            task=task,
            candidate_user_ids=[self.sampler.pk],
            selected_user=self.sampler,
            kind=PersonnelAssignment.Kind.INITIAL,
            is_current=True,
            created_by=self.admin,
        )
        draw_materials(task_id=task.pk, actor=self.sampler)

        response = self.client.get(reverse("management:task-detail", args=[task.pk]))

        self.assertContains(response, task.task_number)
        self.assertContains(response, material.material_number)
        self.assertContains(response, self.sampler.username)
        self.assertContains(response, "版本 1")
        self.assertContains(response, "首次抽样")
        self.assertContains(response, "状态：进行中")
        self.assertNotContains(response, "draw.initial")

    def test_detail_hides_reassignment_when_authorized_redraw_is_pending(self):
        task = self.make_task(status=SamplingTask.Status.ASSIGNED)
        SamplingBatch.objects.create(
            task=task,
            version=2,
            kind=SamplingBatch.Kind.REDRAW,
            status=SamplingBatch.Status.AUTHORIZED,
            reason="样品损坏",
            approved_by=self.admin,
        )

        response = self.client.get(reverse("management:task-detail", args=[task.pk]))

        self.assertTrue(response.context["has_pending_redraw"])
        self.assertFalse(response.context["can_reassign"])
        self.assertNotContains(response, "重新分配原因")

    def test_detail_orders_batches_by_version_and_results_by_sequence(self):
        task = self.make_task(status=SamplingTask.Status.IN_PROGRESS)
        SamplingBatch.objects.create(
            task=task,
            version=2,
            kind=SamplingBatch.Kind.REDRAW,
            status=SamplingBatch.Status.AUTHORIZED,
        )
        version_one = SamplingBatch.objects.create(
            task=task,
            version=1,
            kind=SamplingBatch.Kind.INITIAL,
            status=SamplingBatch.Status.LOCKED,
        )
        second_result = self.add_candidate(task, "RESULT-SECOND")
        first_result = self.add_candidate(task, "RESULT-FIRST")
        SamplingResult.objects.create(
            batch=version_one, material=second_result, sequence=2
        )
        SamplingResult.objects.create(
            batch=version_one, material=first_result, sequence=1
        )

        response = self.client.get(reverse("management:task-detail", args=[task.pk]))

        batch_markup = response.content.decode().split(
            "\u62bd\u6837\u6279\u6b21\u4e0e\u7ed3\u679c", 1
        )[1]
        self.assertLess(
            batch_markup.index("\u7248\u672c 1"),
            batch_markup.index("\u7248\u672c 2"),
        )
        self.assertLess(
            batch_markup.index("RESULT-FIRST"), batch_markup.index("RESULT-SECOND")
        )
