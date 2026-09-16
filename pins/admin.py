from django.contrib import admin

from .models import AutomationSettings, Board, ContentCategory, PinContent, PostLog


@admin.register(ContentCategory)
class ContentCategoryAdmin(admin.ModelAdmin):
    list_display = ("name", "color", "icon")
    prepopulated_fields = {"slug": ("name",)}


@admin.register(Board)
class BoardAdmin(admin.ModelAdmin):
    list_display = ("name", "category", "is_active", "created_at")
    list_filter = ("is_active", "category")
    search_fields = ("name",)


@admin.register(PinContent)
class PinContentAdmin(admin.ModelAdmin):
    list_display = ("title", "board", "category", "status", "scheduled_for", "posted_at", "is_ai_generated")
    list_filter = ("status", "board", "category", "is_ai_generated")
    search_fields = ("title", "description", "hashtags")
    date_hierarchy = "created_at"


@admin.register(AutomationSettings)
class AutomationSettingsAdmin(admin.ModelAdmin):
    list_display = ("is_enabled", "posting_frequency", "default_board", "updated_at")

    def has_add_permission(self, request):
        return not AutomationSettings.objects.exists()


@admin.register(PostLog)
class PostLogAdmin(admin.ModelAdmin):
    list_display = ("pin", "result", "triggered_by", "created_at")
    list_filter = ("result", "triggered_by")
