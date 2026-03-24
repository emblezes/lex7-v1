"""Test de l'agent Veilleur LangChain.

Lance avec :
    python -m legix.scripts.test_veilleur_langchain

Prerequis :
    - Variable ANTHROPIC_API_KEY dans l'environnement ou .env
    - Variable LANGCHAIN_API_KEY pour le tracing LangSmith
    - Base de donnees legix.db peuplee

Tout est visible dans LangSmith : https://smith.langchain.com
"""

import os
import sys

# Config LangSmith — MODIFIE avec ta cle LangSmith
os.environ.setdefault("LANGCHAIN_TRACING_V2", "true")
os.environ.setdefault("LANGCHAIN_PROJECT", "legix-veilleur")
# os.environ["LANGCHAIN_API_KEY"] = "ls-..."  # Decommente et mets ta cle

from legix.agents.langchain_agents import veilleur, chat


def main():
    print("=" * 60)
    print("  AGENT VEILLEUR LANGCHAIN — Test interactif")
    print("  Tout est trace dans LangSmith")
    print("=" * 60)
    print()

    # Questions de test predefinies
    test_questions = [
        "Combien de textes et amendements avons-nous en base ?",
        "Quels sont les derniers textes deposes sur le theme sante ?",
        "Y a-t-il des signaux faibles cette semaine ?",
    ]

    # Mode non-interactif : lance les questions de test
    if "--auto" in sys.argv:
        for q in test_questions:
            print(f"\n>>> {q}")
            print("-" * 40)
            response = chat("veilleur", q)
            print(response)
            print()
        return

    # Mode interactif
    print("Tape ta question (ou 'quit' pour sortir) :\n")
    while True:
        try:
            question = input(">>> ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nAu revoir.")
            break

        if not question or question.lower() in ("quit", "exit", "q"):
            print("Au revoir.")
            break

        print()
        response = chat("veilleur", question)
        print(response)
        print()


if __name__ == "__main__":
    main()
