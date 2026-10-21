"""Orchestrateur de tâches différées : tout ce qui n'est pas critique pour l'affichage.

Le serveur répond dès son démarrage ; les routines lourdes (purge des sauvegardes,
boucle miroir Excel, échauffement OCR) attendent que l'interface ait signalé son
premier rendu via POST /api/ui/ready. Un délai de repli garantit qu'elles
démarreront quand même dans les modes sans fenêtre (headless, mobile seul)
où aucune peinture d'interface ne viendra jamais déclencher le signal.
"""
import sys
import threading

FALLBACK_DELAY = 20.0  # secondes sans signal UI avant de lancer les tâches quand même


class DeferredTasks:
    def __init__(self):
        self._lock = threading.Lock()
        self._pending = []
        self._started = False

    def register(self, name, fn):
        """Enregistre une tâche à exécuter après la peinture de l'interface."""
        with self._lock:
            if self._started:
                fn()
            else:
                self._pending.append((name, fn))

    def start(self):
        """Démarre toutes les tâches enregistrées, une seule fois."""
        with self._lock:
            if self._started:
                return False
            self._started = True
            pending, self._pending = self._pending, []
        if pending:
            threading.Thread(
                target=self._run, args=(pending,), name="deferred-startup", daemon=True
            ).start()
        return True

    @property
    def started(self):
        return self._started

    def _run(self, pending):
        for name, fn in pending:
            try:
                fn()
            except Exception as e:
                print(f"[startup] tâche différée « {name} » échouée : {e}", file=sys.stderr)


deferred_tasks = DeferredTasks()
