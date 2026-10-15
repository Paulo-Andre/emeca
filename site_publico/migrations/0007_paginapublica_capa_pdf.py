from django.core.validators import FileExtensionValidator
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("site_publico", "0006_editor_total_site")]

    operations = [
        migrations.AlterField(
            model_name="paginapublica",
            name="imagem_capa",
            field=models.FileField(
                blank=True,
                upload_to="site_publico/paginas/",
                validators=[FileExtensionValidator(["jpg", "jpeg", "png", "webp", "pdf"])],
            ),
        ),
    ]
