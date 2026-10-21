; eLib – script Inno Setup pour la distribution installée (setup.exe).
; Construit par tools/build_installer_win32.py qui transmet la version :
;   ISCC.exe /DAppVersion=x.y.z installer\eLib.iss
;
; Différences avec les autres distributions :
; - installation machine dans Program Files (x86) + entrée « Applications et fonctionnalités » ;
; - Program Files n'étant pas inscriptible, les données vivent dans {commonappdata}\eLib
;   (C:\ProgramData\eLib) ; l'emplacement est écrit dans elib-data-location.txt à côté
;   de l'exécutable (lu par app/db.py) ;
; - le dossier d'application reçoit un ACL « Users : modifier » pour que la mise à jour
;   automatique (remplacement de eLib.exe au redémarrage) fonctionne sans relance UAC ;
; - la désinstallation ne touche JAMAIS aux données : ProgramData\eLib est conservé.

#ifndef AppVersion
#define AppVersion "0.0.0"
#endif

[Setup]
AppId={{FF49288A-F4CE-5B1B-BA95-BAC8584DF04F}
AppName=eLib
AppVersion={#AppVersion}
VersionInfoVersion={#AppVersion}
AppPublisher=eLib
UninstallDisplayName=eLib
; Sans DisplayIcon, « Applications et fonctionnalités » affiche une icône générique
; (Inno ne l'écrit pas de lui-même) : on pointe sur l'icône de l'exécutable.
UninstallDisplayIcon={app}\eLib.exe
DefaultDirName={autopf}\eLib
DefaultGroupName=eLib
DisableProgramGroupPage=yes
OutputDir=..\dist_win32
OutputBaseFilename=eLib-Setup-{#AppVersion}
SetupIconFile=..\app\static\app-icon.ico
WizardStyle=modern
PrivilegesRequired=admin
Compression=lzma2/max
SolidCompression=yes
MinVersion=10.0

[Languages]
Name: "fr"; MessagesFile: "compiler:Languages\French.isl"

[Tasks]
Name: "desktopicon"; Description: "Créer un raccourci sur le Bureau"; Flags: unchecked

[Files]
Source: "..\dist_win32\eLib.exe"; DestDir: "{app}"; Flags: ignoreversion

[Dirs]
; Users doit pouvoir écrire : la mise à jour automatique remplace eLib.exe ici.
Name: "{app}"; Permissions: users-modify
; Emplacement des données (base, sauvegardes, appairages, journaux de mise à jour).
Name: "{commonappdata}\eLib"; Permissions: users-modify

[Icons]
Name: "{group}\eLib"; Filename: "{app}\eLib.exe"; WorkingDir: "{app}"
Name: "{autodesktop}\eLib"; Filename: "{app}\eLib.exe"; WorkingDir: "{app}"; Tasks: desktopicon

[Run]
Filename: "{app}\eLib.exe"; WorkingDir: "{app}"; Description: "Lancer eLib maintenant"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
; Le marqueur d'emplacement des données part avec l'application (pas avec les données).
Name: "{app}\elib-data-location.txt"; Type: files

[Code]
procedure CurStepChanged(CurStep: TSetupStep);
var
  DataPath, MarkerPath: string;
begin
  if CurStep = ssPostInstall then
  begin
    DataPath := ExpandConstant('{commonappdata}\eLib');
    ForceDirectories(DataPath);
    MarkerPath := ExpandConstant('{app}\elib-data-location.txt');
    SaveStringsToFile(MarkerPath, [DataPath], False);
  end;
end;
