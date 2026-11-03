import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "integration"))

from decision_server import main


def noisy_loader(path):
    print("loader banner on stdout")
    os.write(1, b"raw bytes on fd 1\n")

    def decide(state, questions):
        print("decide banner on stdout")
        return {name: {"answer": True, "probabilities": {"true": 0.9, "false": 0.1}} for name in questions}

    return decide


if __name__ == "__main__":
    main(sys.argv[1:], loader=noisy_loader)
