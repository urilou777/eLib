; eLib – script Inno Setup pour la distribution installée (setup.exe).
; Construit par tools/build_installer_win32.py qui transmet la version :
;   ISCC.exe /DAppVersion=x.y.z installer\eLib.iss                -> setup offline (333 Mo)
;   ISCC.exe /DAppVersion=x.y.z /DWebSetup /DPayloadSha256=...   -> setup web (~2 Mo)
;
; Le mode WebSetup produit un amorçage léger : eLib.exe n'est PAS embarqué,
; il est téléchargé depuis la release GitHub correspondante et vérifié par
; SHA-256 pendant l'installation (même modèle de confiance que la mise à jour
; automatique de l'application). Le mode par défaut embarque eLib.exe pour une
; installation 100% hors-ligne.
;
; Commun aux deux modes :
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

#ifdef WebSetup
  #ifndef PayloadSha256
    #error Le mode WebSetup requiert /DPayloadSha256=<sha256 de eLib.exe>.
  #endif
  #define PayloadUrl "https://github.com/urilou777/eLib/releases/download/v" + AppVersion + "/eLib.exe"
  #define OutputName "eLib-Setup-" + AppVersion
#else
  #define OutputName "eLib-Setup-Offline-" + AppVersion
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
OutputBaseFilename={#OutputName}
SetupIconFile=..\app\static\app-icon.ico
WizardStyle=modern
PrivilegesRequired=admin
MinVersion=10.0
#ifdef WebSetup
Compression=zip
SolidCompression=no
#else
Compression=lzma2/max
SolidCompression=yes
#endif

[Languages]
Name: "fr"; MessagesFile: "compiler:Languages\French.isl"

[Tasks]
Name: "desktopicon"; Description: "Créer un raccourci sur le Bureau"; Flags: unchecked

[Files]
#ifdef WebSetup
; eLib.exe téléchargé dans {tmp} par NextButtonClick (SHA-256 vérifié), installé ensuite.
Source: "{tmp}\eLib.exe"; DestDir: "{app}"; Flags: external ignoreversion
#else
Source: "..\dist_win32\eLib.exe"; DestDir: "{app}"; Flags: ignoreversion
; Le runtime WebView2 voyage à côté de l'exécutable (invisible pour l'utilisateur) :
; c'est ce qui rend le démarrage rapide — l'exe n'a plus 250 Mo à réextraire à chaque lancement.
Source: "..\build_win32\webview2_runtime\Microsoft.WebView2.FixedVersionRuntime.155.0.4283.62.x86\*"; DestDir: "{app}\webview2"; Flags: recursesubdirs createallsubdirs ignoreversion
#endif

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
; Le runtime WebView2 extrait du cab (mode web) n'est pas suivi par le désinstalleur :
; le retirer explicitement (fichiers programme, jamais de données utilisateur).
Name: "{app}\webview2"; Type: filesandordirs

[Code]
#ifdef WebSetup
var
  DownloadPage: TDownloadWizardPage;

procedure InitializeWizard;
begin
  DownloadPage := CreateDownloadPage(SetupMessage(msgWizardPreparing), SetupMessage(msgPreparingDesc), nil);
end;

function NextButtonClick(CurPageID: Integer): Boolean;
var
  Error: String;
begin
  if CurPageID = wpReady then
  begin
    DownloadPage.Clear;
    DownloadPage.Add('{#PayloadUrl}', 'eLib.exe', '{#PayloadSha256}');
    DownloadPage.Add('{#WebviewCabUrl}', 'webview2.cab', '{#WebviewCabSha256}');
    DownloadPage.Show;
    try
      try
        DownloadPage.Download; // télécharge eLib.exe + le runtime WebView2 vers {tmp} (SHA-256 vérifiés)
        Result := True;
      except
        if DownloadPage.AbortedByUser then
          Log('Téléchargement annulé par l''utilisateur.')
        else
        begin
          Error := Format('%s: %s', [DownloadPage.LastBaseNameOrUrl, GetExceptionMessage]);
          SuppressibleMsgBox(
            'Le téléchargement de eLib a échoué (connexion Internet requise). ' + AddPeriod(Error),
            mbCriticalError, MB_OK, IDOK);
        end;
        Result := False;
      end;
    finally
      DownloadPage.Hide;
    end;
  end
  else
    Result := True;
end;
#endif

procedure CurStepChanged(CurStep: TSetupStep);
var
  DataPath, MarkerPath, CabPath, AppDir, RuntimeDir: string;
  ResultCode: Integer;
begin
  if CurStep = ssInstall then
  begin
#ifdef WebSetup
    // Extraire le runtime WebView2 du cab Microsoft (expand.exe, natif Windows)
    // dans {app}, puis renommer le dossier de version en {app}\webview2.
    AppDir := ExpandConstant('{app}');
    ForceDirectories(AppDir);
    CabPath := ExpandConstant('{tmp}\webview2.cab');
    if (not FileExists(CabPath)) or (not Exec(ExpandConstant('{cmd}'),
        '/C expand.exe -F:* "' + CabPath + '" "' + AppDir + '"',
        AppDir, SW_HIDE, ewWaitUntilTerminated, ResultCode)) or (ResultCode <> 0) then
    begin
      SuppressibleMsgBox('L''extraction du runtime WebView2 a échoué (code ' + IntToStr(ResultCode) + ').',
        mbCriticalError, MB_OK, IDOK);
      Abort();
    end;
    RuntimeDir := AppDir + '\Microsoft.WebView2.FixedVersionRuntime.155.0.4283.62.x86';
    if DirExists(RuntimeDir) and (not RenameFile(RuntimeDir, AppDir + '\webview2')) then
    begin
      SuppressibleMsgBox('Impossible d''installer le dossier webview2.', mbCriticalError, MB_OK, IDOK);
      Abort();
    end;
#endif
  end;
  if CurStep = ssPostInstall then
  begin
    DataPath := ExpandConstant('{commonappdata}\eLib');
    ForceDirectories(DataPath);
    MarkerPath := ExpandConstant('{app}\elib-data-location.txt');
    SaveStringsToFile(MarkerPath, [DataPath], False);
  end;
end;
