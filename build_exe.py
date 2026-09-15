"""
build_exe.py  v8.0
=============================================================
Script de compilation PyInstaller — Anaconda Prompt uniquement.

Usage (depuis Anaconda Prompt, dans le dossier du projet) :
    python build_exe.py              -> compile les deux exe
    python build_exe.py ceramique    -> compile coupe_ceramique7_pdf.exe uniquement
    python build_exe.py bloc         -> compile coupe_bloc_pdf.exe uniquement

Produit dans le meme dossier :
    coupe_ceramique7_pdf.exe
    coupe_bloc_pdf.exe

Dependances requises :
    pip install pyinstaller reportlab Pillow opencv-python numpy
"""

import os
import sys
import subprocess
import shutil
import glob

HERE = os.path.dirname(os.path.abspath(__file__))

# ---------------------------------------------------------------------------
# Cibles de compilation
# ---------------------------------------------------------------------------
CIBLES = {
    "ceramique": {
        "script": "coupe_ceramique7_pdf.py",
        "exe":    "coupe_ceramique7_pdf",
        "label":  "Coupe Ceramique PDF",
    },
    "bloc": {
        "script": "coupe_bloc_pdf.py",
        "exe":    "coupe_bloc_pdf",
        "label":  "Coupe Bloc PDF",
    },
}

# ---------------------------------------------------------------------------
def find_mkl_dlls():
    """Cherche les DLL MKL/OpenMP dans l'environnement Anaconda courant."""
    dlls = []
    candidates = [
        os.path.join(sys.prefix, "Library", "bin"),
        os.path.join(sys.prefix, "Library", "mingw-w64", "bin"),
    ]
    try:
        import numpy as np
        candidates.append(os.path.join(os.path.dirname(np.__file__), ".libs"))
    except Exception:
        pass

    patterns = [
        "mkl_intel_thread*.dll", "mkl_core*.dll", "mkl_def*.dll",
        "mkl_avx*.dll", "mkl_rt*.dll", "libiomp5md.dll", "libomp*.dll",
    ]
    for folder in candidates:
        if not os.path.isdir(folder):
            continue
        for pat in patterns:
            for path in glob.glob(os.path.join(folder, pat)):
                if path not in dlls:
                    dlls.append(path)
    return dlls


# ---------------------------------------------------------------------------
def check_prerequisites(script_path):
    """Verifie que le script source et les modules sont disponibles."""
    print("Verification des dependances...")
    errors = []

    if not os.path.isfile(script_path):
        errors.append("Script source introuvable : " + script_path)

    checks = [
        ("PyInstaller",   "PyInstaller", "__version__"),
        ("reportlab",     "reportlab",   "Version"),
        ("Pillow",        "PIL",         "__version__"),
        ("opencv-python", "cv2",         "__version__"),
        ("numpy",         "numpy",       "__version__"),
    ]
    for label, module, attr in checks:
        try:
            mod = __import__(module)
            ver = getattr(mod, attr, "?")
            print("  OK  {0:<16} {1}".format(label, ver))
        except ImportError:
            errors.append("  MANQUANT : {0}  ->  pip install {1}".format(
                label, label.lower()))

    if errors:
        print("\nERREURS :")
        for e in errors:
            print(e)
        print("\nInstallez les modules manquants puis relancez.")
        sys.exit(1)

    print("Toutes les dependances sont presentes.\n")


# ---------------------------------------------------------------------------
def build_one(cible_key):
    """Compile un exe. Retourne le chemin final ou None en cas d'echec."""
    cible       = CIBLES[cible_key]
    script_name = cible["script"]
    exe_name    = cible["exe"]
    label       = cible["label"]

    script_path = os.path.join(HERE, script_name)
    dist_dir    = os.path.join(HERE, "dist")
    build_dir   = os.path.join(HERE, "build_pyinstaller")

    print("=" * 60)
    print("Compilation : {0}".format(label))
    print("  Source : " + script_path)
    print("=" * 60)

    check_prerequisites(script_path)

    mkl_dlls = find_mkl_dlls()
    if mkl_dlls:
        print("DLL MKL/OpenMP trouvees ({0}) :".format(len(mkl_dlls)))
        for d in mkl_dlls:
            print("  " + d)
    else:
        print("AVERTISSEMENT : aucune DLL MKL trouvee.")
        print("  Si l'exe plante avec 'mkl_intel_thread.dll' :")
        print("  conda install -c conda-forge numpy nomkl")
    print()

    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--onefile",
        "--console",
        "--name", exe_name,
        "--distpath", dist_dir,
        "--workpath", build_dir,
        "--specpath", HERE,
        "--clean",
        "--collect-all", "numpy",
        "--collect-all", "cv2",
        "--collect-all", "reportlab",
        "--collect-all", "PIL",
        "--hidden-import", "xml.etree.ElementTree",
        "--hidden-import", "tkinter",
        "--hidden-import", "tkinter.filedialog",
        "--hidden-import", "tempfile",
        "--hidden-import", "traceback",
        "--hidden-import", "math",
        "--hidden-import", "io",
    ]

    for dll in mkl_dlls:
        cmd += ["--add-binary", "{0}{1}.".format(dll, os.pathsep)]

    cmd.append(script_path)

    print("Lancement PyInstaller...")
    result = subprocess.run(cmd, cwd=HERE)

    if result.returncode != 0:
        print("\nECHEC de la compilation (code {0}).".format(result.returncode))
        return None

    exe_ext  = ".exe" if sys.platform == "win32" else ""
    exe_path = os.path.join(dist_dir, exe_name + exe_ext)
    if not os.path.isfile(exe_path):
        exe_path2 = os.path.join(dist_dir, exe_name, exe_name + exe_ext)
        if os.path.isfile(exe_path2):
            exe_path = exe_path2

    if not os.path.isfile(exe_path):
        print("ERREUR : exe introuvable apres compilation.")
        return None

    # Copier dans HERE (a cote des scripts .py)
    dest = os.path.join(HERE, exe_name + exe_ext)
    if os.path.abspath(exe_path) != os.path.abspath(dest):
        shutil.copy2(exe_path, dest)

    size_mb = os.path.getsize(dest) / (1024 * 1024)
    print("\n" + "=" * 60)
    print("SUCCES  {0}".format(label))
    print("  Exe    : " + dest)
    print("  Taille : {0:.1f} Mo".format(size_mb))
    print("=" * 60 + "\n")

    # Nettoyage fichier .spec
    spec_file = os.path.join(HERE, exe_name + ".spec")
    if os.path.isfile(spec_file):
        os.remove(spec_file)
        print("Supprime : " + spec_file)

    return dest


# ---------------------------------------------------------------------------
def main():
    print("build_exe.py  v8.0")
    print("Python  : " + sys.version)
    print("Dossier : " + HERE)
    print()

    # Determiner les cibles a compiler
    arg = sys.argv[1].lower() if len(sys.argv) > 1 else "all"
    if arg in CIBLES:
        keys = [arg]
    elif arg in ("all", "tout"):
        keys = list(CIBLES.keys())
    else:
        print("Usage : python build_exe.py [ceramique|bloc]")
        print("Sans argument : compile les deux.")
        sys.exit(1)

    resultats = {}
    for key in keys:
        exe = build_one(key)
        resultats[key] = exe

    # Nettoyage global dossier build temporaire
    build_dir = os.path.join(HERE, "build_pyinstaller")
    if os.path.isdir(build_dir):
        shutil.rmtree(build_dir, ignore_errors=True)
        print("Supprime : " + build_dir)

    # Bilan final
    print("\n" + "=" * 60)
    print("BILAN DE COMPILATION")
    print("=" * 60)
    tous_ok = True
    for key, exe in resultats.items():
        label = CIBLES[key]["label"]
        if exe:
            print("  OK     {0}".format(label))
            print("         -> " + exe)
        else:
            print("  ECHEC  {0}".format(label))
            tous_ok = False

    print()
    print("Fichiers a placer dans le meme dossier que les .py :")
    print("  lanceur_metashape.py")
    print("  coupe_ceramique7_metashape.py  +  coupe_ceramique7_pdf.exe")
    print("  coupe_bloc_metashape.py        +  coupe_bloc_pdf.exe")
    print("  (+ eventuels PDFs mode_emploi_*.pdf)")
    print("=" * 60)
    print()
    print("NOTE : une fenetre console noire s'ouvre brievement")
    print("pendant la generation du PDF. C'est normal.")

    input("\nAppuyez sur Entree pour fermer...")
    sys.exit(0 if tous_ok else 1)


if __name__ == "__main__":
    main()
