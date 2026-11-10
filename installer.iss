; Установщик EVE LangBridge (Inno Setup 6).
; Собирается скриптом build_exe.py, версия передаётся через /DAppVersion.

#define AppName "EVE LangBridge"
#define AppExe "EVE LangBridge.exe"
#ifndef AppVersion
  #define AppVersion "0.0.0"
#endif

[Setup]
AppId={{7B2E4C1A-5F3D-4A8B-9C6E-2D1F0A9B7C44}
AppName={#AppName}
AppVersion={#AppVersion}
AppVerName={#AppName} {#AppVersion}
AppPublisher={#AppName}
AppPublisherURL=https://github.com/psych3del1c/EVE-LangBridge
AppSupportURL=https://github.com/psych3del1c/EVE-LangBridge/issues
AppUpdatesURL=https://github.com/psych3del1c/EVE-LangBridge/releases
DefaultDirName={localappdata}\Programs\{#AppName}
DefaultGroupName={#AppName}
DisableProgramGroupPage=yes
LicenseFile=LICENSE
; Обычная установка без прав администратора; папку можно выбрать любую.
PrivilegesRequired=lowest
OutputDir=dist
OutputBaseFilename=EVE-LangBridge-{#AppVersion}-setup
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
SetupIconFile=assets\app.ico
UninstallDisplayIcon={app}\{#AppExe}
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
UninstallDisplayName={#AppName}

[Languages]
Name: "russian"; MessagesFile: "compiler:Languages\Russian.isl"
Name: "english"; MessagesFile: "compiler:Default.isl"

[CustomMessages]
russian.DeleteData=Удалить модели и логи?%n%nОни занимают несколько гигабайт. Если оставить, при следующей установке не придётся качать их заново.
english.DeleteData=Delete models and logs?%n%nThey take several gigabytes. If you keep them, a future install won't need to download them again.
russian.AppRunning=Приложение запущено. Закройте его и повторите.
english.AppRunning=The application is running. Please close it and try again.

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"

[Files]
Source: "dist\{#AppName}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#AppName}"; Filename: "{app}\{#AppExe}"
Name: "{group}\{cm:UninstallProgram,{#AppName}}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExe}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#AppExe}"; Description: "{cm:LaunchProgram,{#AppName}}"; Flags: nowait postinstall skipifsilent

[Code]
function InitializeUninstall(): Boolean;
var
  AppExe: String;
begin
  Result := True;
  AppExe := ExpandConstant('{app}\{#AppExe}');
  { Не даём удалять файлы запущенного приложения. }
  if FileExists(AppExe) then
  begin
    if not DeleteFile(AppExe) then
    begin
      MsgBox(ExpandConstant('{cm:AppRunning}'), mbError, MB_OK);
      Result := False;
    end;
  end;
end;

procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
var
  DataDir: String;
begin
  if CurUninstallStep = usPostUninstall then
  begin
    DataDir := ExpandConstant('{app}\data');
    if DirExists(DataDir) then
    begin
      { В тихом режиме ничего не спрашиваем и данные не трогаем. }
      if UninstallSilent then
      begin
      end
      else if MsgBox(ExpandConstant('{cm:DeleteData}'), mbConfirmation, MB_YESNO) = IDYES then
        DelTree(DataDir, True, True, True);
    end;
    { Если папка осталась пустой — убираем и её. }
    RemoveDir(ExpandConstant('{app}'));
  end;
end;
