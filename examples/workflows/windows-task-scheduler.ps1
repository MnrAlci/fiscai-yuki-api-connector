# Voorbeeld (Windows Task Scheduler, PowerShell). [Voorbeeld]-paden; geen geheimen in dit bestand.
# De sleutel wordt als gebruikersvariabele ingesteld buiten dit script (Instellingen > Systeem > Info > Geavanceerd > Omgevingsvariabelen)
# of via Windows Credential Manager; zet hem nooit in het script. Verify current docs: schtasks / Register-ScheduledTask.
$action  = New-ScheduledTaskAction -Execute "yuki-api-connector.exe" -Argument "workflows run -w C:\Yuki\workflows.toml --quiet"
$trigger = New-ScheduledTaskTrigger -Weekly -DaysOfWeek Monday,Tuesday,Wednesday,Thursday,Friday -At 7:30am
Register-ScheduledTask -TaskName "Yuki workflows (voorbeeld)" -Action $action -Trigger $trigger -Description "Voorbereidingen en conceptmails; alleen lezen voor Yuki"
# Powered by FISCALCI Accounting & Tax (Askin Alci)
