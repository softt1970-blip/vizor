// ==UserScript==
// @name         VIZOR Chat Ingest
// @namespace    [http://127.0.0.1/](http://127.0.0.1/)
// @version      1.0
// @description  Перехват кода из чатов ИИ в портативной Mozilla для VIZOR Daemon
// @match        *://*/*
// @grant        GM_xmlhttpRequest
// @connect      127.0.0.1
// ==/UserScript==

(function() {
    'use strict';

    // Горячая клавиша Alt + V для отправки выделенного текста
    document.addEventListener('keydown', function(e) {
        if (e.altKey && (e.key === 'v' || e.key === 'м')) {
            const selectedText = window.getSelection().toString();
            if (!selectedText) {
                alert("VIZOR: Сначала выделите текст ответа ИИ.");
                return;
            }

            GM_xmlhttpRequest({
                method: "POST",
                url: "[http://127.0.0.1:8765/api/ingest](http://127.0.0.1:8765/api/ingest)",
                headers: { "Content-Type": "application/json" },
                data: JSON.stringify({
                    source: window.location.hostname,
                    content: selectedText
                }),
                onload: function(response) {
                    const res = JSON.parse(response.responseText);
                    console.log("VIZOR Response:", res);
                    alert(`VIZOR: Принято файлов: ${res.applied_files.length}\n${res.applied_files.join('\n')}`);
                },
                onerror: function(err) {
                    alert("VIZOR: Сервер не отвечает. Проверьте запуск daemon.py на 127.0.0.1:8765");
                }
            });
        }
    });
})();
