from django.db import migrations, models
from django.db.models import Sum


def preencher_faltas_totais(apps, schema_editor):
    BoletimAluno = apps.get_model("site_publico", "BoletimAluno")
    NotaBoletim = apps.get_model("site_publico", "NotaBoletim")

    for boletim in BoletimAluno.objects.all().iterator():
        total = (
            NotaBoletim.objects
            .filter(boletim_id=boletim.pk, faltas__isnull=False)
            .aggregate(total=Sum("faltas"))
            .get("total")
        )
        if total is not None:
            boletim.faltas_totais = total
            boletim.save(update_fields=["faltas_totais"])


class Migration(migrations.Migration):
    dependencies = [("site_publico", "0010_boletins")]

    operations = [
        migrations.AddField(
            model_name="boletimaluno",
            name="faltas_totais",
            field=models.PositiveSmallIntegerField(blank=True, null=True),
        ),
        migrations.RunPython(
            preencher_faltas_totais,
            migrations.RunPython.noop,
        ),
    ]
