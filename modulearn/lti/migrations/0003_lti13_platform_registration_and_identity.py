from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("lti", "0002_add_module_tracking_fields"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="LTIPlatformRegistration",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("name", models.CharField(max_length=255)),
                (
                    "platform",
                    models.CharField(
                        choices=[("canvas", "Canvas"), ("moodle", "Moodle"), ("other", "Other")],
                        default="other",
                        max_length=32,
                    ),
                ),
                ("issuer", models.URLField(help_text="Platform ID / issuer URL", max_length=512)),
                ("client_id", models.CharField(max_length=255)),
                ("deployment_ids", models.JSONField(blank=True, default=list)),
                ("auth_login_url", models.URLField(help_text="Platform authentication request URL", max_length=512)),
                ("auth_token_url", models.URLField(help_text="Platform access token URL", max_length=512)),
                ("key_set_url", models.URLField(help_text="Platform public keyset URL", max_length=512)),
                ("auth_audience", models.URLField(blank=True, default="", max_length=512)),
                ("is_active", models.BooleanField(default=True)),
                ("notes", models.TextField(blank=True, default="")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={
                "verbose_name": "LTI 1.3 Platform Registration",
                "verbose_name_plural": "LTI 1.3 Platform Registrations",
            },
        ),
        migrations.CreateModel(
            name="LTIUserIdentity",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("issuer", models.CharField(max_length=512)),
                ("client_id", models.CharField(blank=True, default="", max_length=255)),
                ("deployment_id", models.CharField(blank=True, default="", max_length=255)),
                ("subject", models.CharField(max_length=255)),
                ("last_launch_data", models.JSONField(blank=True, default=dict)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("last_seen_at", models.DateTimeField(auto_now=True)),
                (
                    "platform_registration",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="user_identities",
                        to="lti.ltiplatformregistration",
                    ),
                ),
                (
                    "user",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="lti_identities",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "verbose_name": "LTI User Identity",
                "verbose_name_plural": "LTI User Identities",
            },
        ),
        migrations.AddIndex(
            model_name="ltiplatformregistration",
            index=models.Index(fields=["issuer", "client_id"], name="lti_ltiplat_issuer_b30e7f_idx"),
        ),
        migrations.AddIndex(
            model_name="ltiplatformregistration",
            index=models.Index(fields=["platform", "is_active"], name="lti_ltiplat_platfor_2dfe0d_idx"),
        ),
        migrations.AddConstraint(
            model_name="ltiplatformregistration",
            constraint=models.UniqueConstraint(
                fields=("issuer", "client_id"),
                name="lti_platform_registration_issuer_client_unique",
            ),
        ),
        migrations.AddIndex(
            model_name="ltiuseridentity",
            index=models.Index(fields=["issuer", "client_id"], name="lti_ltiuser_issuer_2f6f0e_idx"),
        ),
        migrations.AddIndex(
            model_name="ltiuseridentity",
            index=models.Index(fields=["subject"], name="lti_ltiuser_subject_167c61_idx"),
        ),
        migrations.AddConstraint(
            model_name="ltiuseridentity",
            constraint=models.UniqueConstraint(
                fields=("issuer", "client_id", "subject"),
                name="lti_user_identity_unique_subject_per_client",
            ),
        ),
    ]
