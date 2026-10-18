"""QA do patcher WA-AKG sem acessar o servidor ou mensagens reais."""
import importlib.util
import pathlib
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
ARQUIVO = ROOT / "deploy" / "wa-akg" / "aplicar_correcoes.py"
SPEC = importlib.util.spec_from_file_location("aplicar_correcoes", ARQUIVO)
MOD = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MOD)


class SchedulerUnicoTests(unittest.TestCase):
    def test_desativa_importacao_e_inicializacao_antigas(self):
        antigo = (
            'import { initScheduler } from "@/lib/cron";\n'
            "export class Manager {\n"
            "  constructor() {\n"
            "        initScheduler();\n"
            "  }\n}\n"
        )
        novo = MOD.desativar_agendador_duplicado(antigo)
        self.assertNotIn("initScheduler", novo)
        self.assertIn("Agendamento centralizado em", novo)
        self.assertEqual(MOD.desativar_agendador_duplicado(novo), novo)

    def test_reconhece_correcao_manual_ja_existente(self):
        atual = (
            "        // Agendamento centralizado em "
            "src/modules/whatsapp/scheduler.ts\n"
            "const socket = true;\n"
        )
        self.assertEqual(MOD.desativar_agendador_duplicado(atual), atual)

    def test_bloqueia_alteracoes_desconhecidas_do_manager(self):
        with self.assertRaises(RuntimeError):
            MOD.desativar_agendador_duplicado("export class Manager {}\n")
        with self.assertRaises(RuntimeError):
            MOD.desativar_agendador_duplicado(
                'import { initScheduler } from "@/lib/cron";\n'
                "  this.initScheduler();\n"
            )

    def test_recusa_outras_referencias_ao_antigo_agendador(self):
        codigo = (
            'import { initScheduler } from "@/lib/cron";\n'
            "        initScheduler();\n"
            "        initScheduler();\n"
        )
        with self.assertRaises(RuntimeError):
            MOD.desativar_agendador_duplicado(codigo)

    def test_scheduler_usa_claim_atomico_antes_de_send_message(self):
        fonte = (
            ROOT / "deploy" / "wa-akg" / "overrides" / "src"
            / "modules" / "whatsapp" / "scheduler.ts"
        ).read_text(encoding="utf-8")
        self.assertIn('status: "PENDING"', fonte)
        self.assertIn('status: "PROCESSING"', fonte)
        self.assertIn('claim.count !== 1', fonte)
        self.assertIn('status: "FAILED"', fonte)
        self.assertLess(
            fonte.index("claim.count !== 1"),
            fonte.index("instance.socket.sendMessage(msg.jid, content)"),
        )
        self.assertIn('status: "PROCESSING" },', fonte)



    def test_recorrencias_sao_reagendadas_apos_aceite_e_no_fuso_local(self):
        fonte = (
            ROOT / "deploy" / "wa-akg" / "overrides" / "src"
            / "modules" / "whatsapp" / "scheduler.ts"
        ).read_text(encoding="utf-8")
        self.assertIn('CronExpressionParser.parse(', fonte)
        self.assertIn('process.env.TZ || "America/Sao_Paulo"', fonte)
        self.assertIn('if (msg.cronExpression)', fonte)
        self.assertIn('data: { status: "PENDING", sendAt: proxima }', fonte)
        self.assertLess(
            fonte.index("instance.socket.sendMessage(msg.jid, content)"),
            fonte.index('data: { status: "PENDING", sendAt: proxima }'),
        )
        self.assertNotIn("Asia/Jakarta", fonte)




if __name__ == "__main__":
    unittest.main()
