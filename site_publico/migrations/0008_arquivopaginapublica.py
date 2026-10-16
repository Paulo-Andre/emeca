from django.core.validators import FileExtensionValidator
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [("site_publico", "0007_paginapublica_capa_pdf")]

    operations = [
        migrations.CreateModel(
            name="ArquivoPaginaPublica",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("titulo", models.CharField(blank=True, max_length=180)),
                ("arquivo", models.FileField(
                    upload_to="site_publico/paginas/documentos/",
                    validators=[FileExtensionValidator(["pdf", "doc", "docx", "xls", "xlsx", "odt"])],
                )),
                ("ativo", models.BooleanField(default=True)),
                ("ordem", models.PositiveSmallIntegerField(default=0)),
                ("criado_em", models.DateTimeField(auto_now_add=True)),
                ("pagina", models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name="arquivos",
                    to="site_publico.paginapublica",
                )),
            ],
            options={
                "verbose_name": "Documento da página",
                "verbose_name_plural": "Documentos da página",
                "ordering": ["ordem", "id"],
            },
        ),
    ]
