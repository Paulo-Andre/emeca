"""Regression tests for the guarded WA-AKG message store patch.

Run locally without a WhatsApp connection:
python3 -m unittest discover -s deploy/wa-akg -p 'test_*.py'
"""
import importlib.util
from pathlib import Path
import unittest


here = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location(
    "emeca_wa_akg_patcher", here / "aplicar_correcoes.py"
)
patcher = importlib.util.module_from_spec(spec)
spec.loader.exec_module(patcher)

GUARD = """        // Ensure we have the database session ID
        if (!dbSessionId) {
            const session = await prisma.session.findUnique({ where: { sessionId }, select: { id: true } });
            if (!session) return;
            dbSessionId = session.id;
        }"""

LIVE_CATCH = """            } catch (error) {
                logger.error("Store", "Error saving message", error);
            }"""

HISTORY_CATCH = """                } catch (error) {
                    logger.error("Store", "Error saving historical message", error);
                }"""

CREATE_CATCH = """    } catch (e: any) {
        logger.error("Store", "Error saving message query", e);
        throw e;
    }"""


class StorePatchTests(unittest.TestCase):
    def setUp(self):
        self.original = (
            "// listener: messages.upsert\n" + GUARD + "\n" +
            LIVE_CATCH + "\n" +
            "// listener: messaging-history.set\n" + GUARD + "\n" +
            HISTORY_CATCH + "\n" +
            "// listener: contacts.upsert\n" + GUARD + "\n" +
            CREATE_CATCH + "\n"
        )

    def test_only_message_listeners_validate_current_internal_session(self):
        changed = patcher.corrigir_gravacao_mensagens_emeca(self.original)
        self.assertEqual(changed.count("const currentStoreSession ="), 2)
        self.assertEqual(changed.count(GUARD), 1)
        self.assertIn('if (e?.code === "P2002") return null;', changed)
        self.assertEqual(changed.count('error?.code === "P2003"'), 2)
        self.assertIn("break;", changed)
        self.assertIn("// listener: contacts.upsert\n" + GUARD, changed)

    def test_idempotent(self):
        once = patcher.corrigir_gravacao_mensagens_emeca(self.original)
        twice = patcher.corrigir_gravacao_mensagens_emeca(once)
        self.assertEqual(once, twice)

    def test_unknown_store_is_rejected_without_changes(self):
        with self.assertRaises(RuntimeError):
            patcher.corrigir_gravacao_mensagens_emeca("custom store")

    def test_partial_patch_is_rejected(self):
        changed = patcher.corrigir_gravacao_mensagens_emeca(self.original)
        with self.assertRaises(RuntimeError):
            patcher.corrigir_gravacao_mensagens_emeca(
                changed.replace("const currentStoreSession", "const alteredSession", 1)
            )


if __name__ == "__main__":
    unittest.main()
