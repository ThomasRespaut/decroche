# twilio_bridge/admin.py

from django.contrib import admin, messages
from django.utils.html import format_html
from django.urls import path
from django.shortcuts import redirect

from .models import OutboundCall
from .services import launch_outbound_call


@admin.register(OutboundCall)
class OutboundCallAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "to_number",
        "status",
        "call_sid",
        "created_at",
        "launch_button",
    )

    readonly_fields = (
        "call_sid",
        "status",
        "duration",
        "created_at",
        "updated_at",
    )

    # 🔹 Ajoute une route custom dans l’admin
    def get_urls(self):
        urls = super().get_urls()
        custom_urls = [
            path(
                "<int:call_id>/launch/",
                self.admin_site.admin_view(self.launch_call_view),
                name="outboundcall-launch",
            ),
        ]
        return custom_urls + urls

    # 🔹 Bouton dans la liste admin
    def launch_button(self, obj):
        if not obj.call_sid:
            return format_html(
                '<a class="button" href="{}">Lancer</a>',
                f"{obj.id}/launch/"
            )
        return "Déjà lancé"

    launch_button.short_description = "Action"

    # 🔹 Vue qui déclenche l'appel
    def launch_call_view(self, request, call_id):
        call_obj = OutboundCall.objects.get(pk=call_id)

        try:
            call = launch_outbound_call(
                call_obj.to_number,
                call_obj.prospect_name,
                call_obj.company,
                call_obj.custom_prompt,
            )

            call_obj.call_sid = call.sid
            call_obj.status = "initiated"
            call_obj.save()

            messages.success(request, f"Appel lancé (SID: {call.sid})")

        except Exception as e:
            messages.error(request, f"Erreur : {str(e)}")

        return redirect(
            f"/admin/twilio_bridge/outboundcall/{call_id}/change/"
        )