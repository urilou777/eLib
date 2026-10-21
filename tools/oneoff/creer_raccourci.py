import os
import sys

try:
    desktop = os.path.join(os.path.expanduser("~"), "Desktop")
    bat_path = os.path.abspath("Lancer_eLib.bat")
    working_dir = os.path.abspath(".")
    ico_path = os.path.abspath(os.path.join("app", "static", "app-icon.ico"))

    vbs_content = f'''Set oWS = WScript.CreateObject("WScript.Shell")
sLinkFile = "{desktop}\\eLib.lnk"
Set oLink = oWS.CreateShortcut(sLinkFile)
oLink.TargetPath = "{bat_path}"
oLink.WorkingDirectory = "{working_dir}"
oLink.Description = "Lancer la Librairie Chrétienne"
If "{ico_path}" <> "" Then
    oLink.IconLocation = "{ico_path}, 0"
End If
oLink.Save
'''
    vbs_path = os.path.abspath("create_shortcut.vbs")
    with open(vbs_path, "w", encoding="latin-1") as f:
        f.write(vbs_content)
    os.system(f'cscript //nologo "{vbs_path}"')
    if os.path.exists(vbs_path):
        os.remove(vbs_path)
    print("Raccourci Bureau créé avec succès sur :", os.path.join(desktop, "eLib.lnk"))
except Exception as e:
    print("Erreur création raccourci :", e)
