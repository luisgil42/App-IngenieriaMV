# finanzas_comercial/urls.py
from django.urls import path

from . import views_company as company_views
from . import views_contacto, views_cotizaciones, views_deals, views_tareas

app_name = "finanzas_comercial"

urlpatterns = [
    path("", views_contacto.index, name="index"),  # ✅ solo uno

    # Contactos
    path("contactos/", views_contacto.contact_list, name="contact_list"),
    path("contactos/nuevo/", views_contacto.contact_create, name="contact_create"),
    path("contactos/<int:pk>/editar/", views_contacto.contact_edit, name="contact_edit"),
    path("contactos/<int:pk>/eliminar/", views_contacto.contact_delete, name="contact_delete"),

    # Excel
    path("contactos/exportar.xlsx", views_contacto.contact_export_xlsx, name="contact_export_xlsx"),
    path("contactos/importar/", views_contacto.contact_import, name="contact_import"),
    path("contactos/importar/formato.xlsx", views_contacto.contact_import_template_xlsx, name="contact_import_template_xlsx"),

        # Empresas
    path("empresas/", company_views.company_list, name="company_list"),
    path("empresas/crear/", company_views.company_create, name="company_create"),
    path("empresas/<int:pk>/editar/", company_views.company_edit, name="company_edit"),
    path("empresas/<int:pk>/eliminar/", company_views.company_delete, name="company_delete"),
    path("empresas/exportar.xlsx", company_views.company_export_xlsx, name="company_export_xlsx"),
    path("empresas/importar/", company_views.company_import, name="company_import"),
    path("empresas/importar/formato.xlsx", company_views.company_import_template_xlsx, name="company_import_template_xlsx"),

    # NEGOCIOS
    path("negocios/", views_deals.deal_list, name="deal_list"),
    path("negocios/crear/", views_deals.deal_create, name="deal_create"),
    path("negocios/<int:pk>/editar/", views_deals.deal_edit, name="deal_edit"),
    path("negocios/<int:pk>/eliminar/", views_deals.deal_delete, name="deal_delete"),
    path("negocios/<int:pk>/analisis/", views_deals.deal_analysis_upload, name="deal_analysis_upload"),
    path("deals/attachments/<int:pk>/delete/", views_deals.deal_attachment_delete, name="deal_attachment_delete"),

    path("negocios/exportar.xlsx", views_deals.deal_export_xlsx, name="deal_export_xlsx"),
    path("negocios/importar/", views_deals.deal_import, name="deal_import"),

    # ETAPAS (se gestionan desde la vista de negocios, pero endpoints separados)
    path("negocios/etapas/crear/", views_deals.deal_stage_create, name="deal_stage_create"),
    path("negocios/etapas/<int:pk>/editar/", views_deals.deal_stage_edit, name="deal_stage_edit"),
    path("negocios/etapas/<int:pk>/eliminar/", views_deals.deal_stage_delete, name="deal_stage_delete"),

  # tareas
    path("tareas/", views_tareas.task_list, name="task_list"),
    path("tareas/crear/", views_tareas.task_create, name="task_create"),
    path("tareas/<int:pk>/editar/", views_tareas.task_edit, name="task_edit"),
    path("tareas/<int:pk>/eliminar/", views_tareas.task_delete, name="task_delete"),
    path("tareas/<int:pk>/estatus/", views_tareas.task_update_status, name="task_update_status"),

# cotizaciones
    path("cotizaciones/", views_cotizaciones.quote_list, name="quote_list"),
    path("cotizaciones/crear/", views_cotizaciones.quote_create, name="quote_create"),
    path("cotizaciones/<int:pk>/editar/", views_cotizaciones.quote_edit, name="quote_edit"),
    path("cotizaciones/<int:pk>/eliminar/", views_cotizaciones.quote_delete, name="quote_delete"),
    path("cotizaciones/<int:pk>/duplicar/", views_cotizaciones.quote_duplicate, name="quote_duplicate"),
    path("cotizaciones/<int:pk>/estado/", views_cotizaciones.quote_update_status, name="quote_update_status"),
    path("cotizaciones/<int:pk>/pdf/", views_cotizaciones.quote_pdf_download, name="quote_pdf_download"),

]



