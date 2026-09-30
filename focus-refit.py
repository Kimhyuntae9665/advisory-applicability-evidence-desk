"""Run the original browser keyboard regression against the refit without overwriting history."""
from pathlib import Path

root=Path(__file__).resolve().parent
text=(root/'focus-check.py').read_text()
text=text.replace("s.listen(0,'127.0.0.1'", "s.listen(5158,'127.0.0.1'")
text=text.replace("out = ROOT / 'artifacts' / f'keyboard-focus-{expect}.json'", "out = ROOT / 'artifacts' / 'ui-refit' / f'keyboard-focus-{expect}.json'")
(root/'artifacts/ui-refit').mkdir(parents=True,exist_ok=True)
exec(compile(text,str(root/'focus-check.py'),'exec'),{'__name__':'__main__','__file__':str(root/'focus-check.py')})
