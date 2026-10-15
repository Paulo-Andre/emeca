import sqlite3
from pathlib import Path

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from historico.models import (
    Aluno,
    AuditoriaEvento,
    ConfiguracaoAno,
    DocumentoHistorico,
    MatrizComponente,
    MatrizCurricularVersao,
    Nota,
    RegistroAcademico,
)


MODELOS = [
    MatrizCurricularVersao,
    MatrizComponente,
    Aluno,
    ConfiguracaoAno,
    RegistroAcademico,
    Nota,
    DocumentoHistorico,
    AuditoriaEvento,
]


class Command(BaseCommand):
    help = (
        "Migra integralmente o banco SQLite do antigo historico_egidio para "
        "o banco unificado. O banco de origem nunca e alterado."
    )

    def add_arguments(self, parser):
        parser.add_argument("arquivo", help="Caminho para o historico.sqlite3 antigo")
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Valida origem e mostra contagens sem gravar nada.",
        )

    def _table_exists(self, conn, table):
        return conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
            (table,),
        ).fetchone() is not None

    def _rows(self, conn, table):
        if not self._table_exists(conn, table):
            raise CommandError(f"Tabela ausente no banco legado: {table}")
        return conn.execute(f'SELECT * FROM "{table}"').fetchall()

    def _model_kwargs(self, model, row):
        by_column = {field.column: field.attname for field in model._meta.fields}
        return {
            by_column[column]: row[column]
            for column in row.keys()
            if column in by_column
        }

    def _target_has_historico_data(self):
        return any(model.objects.exists() for model in MODELOS)

    def _copy_users(self, conn, dry_run):
        User = get_user_model()
        table = User._meta.db_table
        if not self._table_exists(conn, table):
            return {}, 0

        source_rows = self._rows(conn, table)
        mapping = {}
        created = 0

        for row in source_rows:
            username = row["username"]
            existing = User.objects.filter(username=username).first()
            if existing:
                mapping[row["id"]] = existing.pk
                continue

            if dry_run:
                mapping[row["id"]] = None
                created += 1
                continue

            values = {
                "username": username,
                "password": row["password"],
                "last_login": row["last_login"],
                "is_superuser": bool(row["is_superuser"]),
                "first_name": row["first_name"],
                "last_name": row["last_name"],
                "email": row["email"],
                "is_staff": bool(row["is_staff"]),
                "is_active": bool(row["is_active"]),
                "date_joined": row["date_joined"],
            }
            user = User.objects.create(**values)
            mapping[row["id"]] = user.pk
            created += 1

        return mapping, created

    def _copy_model(self, conn, model, user_mapping, dry_run):
        table = model._meta.db_table
        rows = self._rows(conn, table)

        if dry_run:
            return len(rows)

        objects = []
        timestamps = []

        for row in rows:
            kwargs = self._model_kwargs(model, row)

            if model is DocumentoHistorico:
                old_user = kwargs.get("emitido_por_id")
                kwargs["emitido_por_id"] = user_mapping.get(old_user) if old_user else None
                timestamps.append((kwargs["id"], row["emitido_em"]))
            elif model is AuditoriaEvento:
                old_user = kwargs.get("usuario_id")
                kwargs["usuario_id"] = user_mapping.get(old_user) if old_user else None
                timestamps.append((kwargs["id"], row["criado_em"]))

            objects.append(model(**kwargs))

        if objects:
            model.objects.bulk_create(objects, batch_size=500)

        # auto_now_add substitui o valor durante a insercao; restaura a data original.
        if model is DocumentoHistorico:
            for pk, value in timestamps:
                model.objects.filter(pk=pk).update(emitido_em=value)
        elif model is AuditoriaEvento:
            for pk, value in timestamps:
                model.objects.filter(pk=pk).update(criado_em=value)

        return len(rows)

    @transaction.atomic
    def handle(self, *args, **options):
        source = Path(options["arquivo"]).expanduser().resolve()
        dry_run = options["dry_run"]

        if not source.exists() or not source.is_file():
            raise CommandError(f"Banco legado nao encontrado: {source}")

        if source.stat().st_size == 0:
            raise CommandError(f"Banco legado esta vazio: {source}")

        if not dry_run and self._target_has_historico_data():
            raise CommandError(
                "O banco unificado ja possui dados do Historico. "
                "A migracao foi cancelada para evitar duplicacao/sobrescrita."
            )

        conn = sqlite3.connect(f"file:{source}?mode=ro", uri=True)
        conn.row_factory = sqlite3.Row

        try:
            user_mapping, users_created = self._copy_users(conn, dry_run)
            counts = {}

            for model in MODELOS:
                counts[model.__name__] = self._copy_model(
                    conn, model, user_mapping, dry_run
                )

            prefix = "Validacao concluida" if dry_run else "Migracao concluida"
            self.stdout.write(self.style.SUCCESS(prefix + "."))
            self.stdout.write(
                f"Usuarios novos: {users_created}; "
                + "; ".join(f"{name}: {count}" for name, count in counts.items())
            )
            if dry_run:
                self.stdout.write(
                    "Nenhuma alteracao foi feita. Execute novamente sem --dry-run para migrar."
                )
        finally:
            conn.close()
