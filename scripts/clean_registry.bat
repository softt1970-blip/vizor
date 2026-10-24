@ echo off 
REM Пример удаления ключа остатков программы 
reg delete "HKCU\Software\Название_Вашей_Программы" /f 
reg delete "HKLM\SOFTWARE\Название_Вашей_Программы" /f 
echo Удаление завершено. 
pause
