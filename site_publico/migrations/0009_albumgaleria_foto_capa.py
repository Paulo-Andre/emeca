from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [("site_publico", "0008_arquivopaginapublica")]

    operations = [
        migrations.AddField(
            model_name="albumgaleria",
            name="foto_capa",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="+",
                to="site_publico.fotogaleria",
            ),
        ),
    ]
