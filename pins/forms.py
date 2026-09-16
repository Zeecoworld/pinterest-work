from django import forms

from .models import AutomationSettings, Board, ContentCategory, PinContent

BASE_INPUT = (
    "w-full rounded-xl border border-slate-200 bg-white px-3.5 py-2.5 text-sm text-slate-800 "
    "placeholder:text-slate-400 shadow-sm transition focus:border-indigo-500 focus:ring-4 "
    "focus:ring-indigo-100 focus:outline-none"
)
BASE_SELECT = BASE_INPUT + " appearance-none"
BASE_CHECKBOX = (
    "h-5 w-5 rounded-md border-slate-300 text-indigo-600 focus:ring-indigo-500 focus:ring-offset-0"
)


class PinContentForm(forms.ModelForm):
    class Meta:
        model = PinContent
        fields = [
            "title",
            "description",
            "image",
            "alt_text",
            "destination_link",
            "board",
            "category",
            "hashtags",
            "status",
            "scheduled_for",
            "is_ai_generated",
            "ai_prompt",
        ]
        widgets = {
            "title": forms.TextInput(
                attrs={"class": BASE_INPUT, "placeholder": "e.g. 5 AI Tools Every Developer Needs in 2026"}
            ),
            "description": forms.Textarea(
                attrs={
                    "class": BASE_INPUT,
                    "rows": 4,
                    "placeholder": "Write a keyword-rich description Pinterest search will love…",
                }
            ),
            "image": forms.ClearableFileInput(
                attrs={"class": "hidden", "accept": "image/*", "x-ref": "fileInput"}
            ),
            "alt_text": forms.TextInput(
                attrs={"class": BASE_INPUT, "placeholder": "Describe the image for accessibility"}
            ),
            "destination_link": forms.URLInput(
                attrs={"class": BASE_INPUT, "placeholder": "https://zeecomedia.com/blog/…"}
            ),
            "board": forms.Select(attrs={"class": BASE_SELECT}),
            "category": forms.Select(attrs={"class": BASE_SELECT}),
            "hashtags": forms.TextInput(
                attrs={"class": BASE_INPUT, "placeholder": "#AI #WebDevelopment #TechTips"}
            ),
            "status": forms.Select(attrs={"class": BASE_SELECT}),
            "scheduled_for": forms.DateTimeInput(
                attrs={"class": BASE_INPUT, "type": "datetime-local"}, format="%Y-%m-%dT%H:%M"
            ),
            "is_ai_generated": forms.CheckboxInput(attrs={"class": BASE_CHECKBOX}),
            "ai_prompt": forms.HiddenInput(),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["scheduled_for"].input_formats = ["%Y-%m-%dT%H:%M"]
        self.fields["board"].queryset = Board.objects.filter(is_active=True)
        self.fields["category"].required = False
        self.fields["destination_link"].required = False
        self.fields["alt_text"].required = False
        self.fields["hashtags"].required = False
        self.fields["ai_prompt"].required = False


class BoardForm(forms.ModelForm):
    class Meta:
        model = Board
        fields = ["name", "category", "description", "is_active"]
        widgets = {
            "name": forms.TextInput(attrs={"class": BASE_INPUT, "placeholder": "AI & Automation"}),
            "category": forms.Select(attrs={"class": BASE_SELECT}),
            "description": forms.Textarea(attrs={"class": BASE_INPUT, "rows": 3}),
            "is_active": forms.CheckboxInput(attrs={"class": BASE_CHECKBOX}),
        }


class ContentCategoryForm(forms.ModelForm):
    class Meta:
        model = ContentCategory
        fields = ["name", "color", "icon"]
        widgets = {
            "name": forms.TextInput(attrs={"class": BASE_INPUT, "placeholder": "AI News"}),
            "color": forms.TextInput(attrs={"class": BASE_INPUT + " h-11 w-20 p-1", "type": "color"}),
            "icon": forms.TextInput(attrs={"class": BASE_INPUT, "placeholder": "sparkles"}),
        }


class AutomationSettingsForm(forms.ModelForm):
    class Meta:
        model = AutomationSettings
        fields = [
            "is_enabled",
            "pinterest_access_token",
            "pinterest_app_id",
            "default_board",
            "posting_frequency",
            "custom_interval_hours",
            "daily_start_time",
            "daily_end_time",
            "post_monday",
            "post_tuesday",
            "post_wednesday",
            "post_thursday",
            "post_friday",
            "post_saturday",
            "post_sunday",
            "auto_generate_hashtags",
            "only_post_ai_flagged_content",
            "default_ai_image_style",
            "notify_on_failure",
            "notification_email",
        ]
        widgets = {
            "is_enabled": forms.CheckboxInput(attrs={"class": "peer sr-only"}),
            "pinterest_access_token": forms.PasswordInput(
                attrs={"class": BASE_INPUT, "placeholder": "pina_••••••••••••••••", "render_value": True},
            ),
            "pinterest_app_id": forms.TextInput(attrs={"class": BASE_INPUT, "placeholder": "1234567"}),
            "default_board": forms.Select(attrs={"class": BASE_SELECT}),
            "posting_frequency": forms.Select(attrs={"class": BASE_SELECT}),
            "custom_interval_hours": forms.NumberInput(attrs={"class": BASE_INPUT, "min": 1, "max": 24}),
            "daily_start_time": forms.TimeInput(attrs={"class": BASE_INPUT, "type": "time"}),
            "daily_end_time": forms.TimeInput(attrs={"class": BASE_INPUT, "type": "time"}),
            "post_monday": forms.CheckboxInput(attrs={"class": BASE_CHECKBOX}),
            "post_tuesday": forms.CheckboxInput(attrs={"class": BASE_CHECKBOX}),
            "post_wednesday": forms.CheckboxInput(attrs={"class": BASE_CHECKBOX}),
            "post_thursday": forms.CheckboxInput(attrs={"class": BASE_CHECKBOX}),
            "post_friday": forms.CheckboxInput(attrs={"class": BASE_CHECKBOX}),
            "post_saturday": forms.CheckboxInput(attrs={"class": BASE_CHECKBOX}),
            "post_sunday": forms.CheckboxInput(attrs={"class": BASE_CHECKBOX}),
            "auto_generate_hashtags": forms.CheckboxInput(attrs={"class": BASE_CHECKBOX}),
            "only_post_ai_flagged_content": forms.CheckboxInput(attrs={"class": BASE_CHECKBOX}),
            "default_ai_image_style": forms.TextInput(
                attrs={"class": BASE_INPUT, "placeholder": "flat vector illustration, vibrant colors…"}
            ),
            "notify_on_failure": forms.CheckboxInput(attrs={"class": BASE_CHECKBOX}),
            "notification_email": forms.EmailInput(
                attrs={"class": BASE_INPUT, "placeholder": "you@zeecomedia.com"}
            ),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["default_board"].required = False
        self.fields["pinterest_access_token"].required = False
        self.fields["pinterest_app_id"].required = False
        self.fields["notification_email"].required = False
        self.fields["default_ai_image_style"].required = False
