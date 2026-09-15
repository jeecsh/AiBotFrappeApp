// ERPNext AI - Chat Button and Auth Handler
(function() {
    // Configuration - change this to your AI backend URL
    const AI_URL = "https://ai.nos-lab.com/chat";

    // Prevent duplicate initialization
    if (document.getElementById("erpnext-ai-btn")) return;

    // Create floating button
    const btn = document.createElement("div");
    btn.id = "erpnext-ai-btn";
    btn.innerHTML = '<img src="' + AI_URL.replace('/chat', '') + '/logo.png" style="width:48px;height:48px;">';
    btn.style.cssText = "position:fixed;bottom:20px;right:20px;cursor:pointer;z-index:1000;transition:transform 0.2s;";
    btn.onmouseenter = function() { this.style.transform = "scale(1.1)"; };
    btn.onmouseleave = function() { this.style.transform = "scale(1)"; };
    document.body.appendChild(btn);

    // Create chat panel
    const panel = document.createElement("div");
    panel.id = "erpnext-ai-panel";
    panel.style.cssText = "position:fixed;bottom:80px;right:20px;width:380px;height:520px;border-radius:12px;box-shadow:0 4px 24px rgba(0,0,0,0.15);display:none;z-index:1001;overflow:hidden;background:white;";

    const iframe = document.createElement("iframe");
    iframe.src = AI_URL;
    iframe.style.cssText = "width:100%;height:100%;border:none;";
    panel.appendChild(iframe);
    document.body.appendChild(panel);

    // Handle messages from iframe
    window.addEventListener("message", function(e) {
        // When iframe is ready, send credentials
        if (e.data && e.data.type === "NOS_AI_READY") {
            frappe.call({
                method: "erpnext_ai.api.get_credentials",
                async: true,
                callback: function(r) {
                    if (r.message) {
                        iframe.contentWindow.postMessage({
                            type: "NOS_AI_CREDENTIALS",
                            apiKey: r.message.api_key,
                            apiSecret: r.message.api_secret,
                            user: r.message.user
                        }, "*");
                    }
                },
                error: function(r) {
                    iframe.contentWindow.postMessage({
                        type: "NOS_AI_CREDENTIALS",
                        error: "Could not get credentials. Please try again."
                    }, "*");
                }
            });
        }
    });

    // Toggle panel on button click
    btn.onclick = function() {
        panel.style.display = panel.style.display === "none" ? "block" : "none";
    };

    // Close on Escape key
    document.addEventListener("keydown", function(e) {
        if (e.key === "Escape" && panel.style.display !== "none") {
            panel.style.display = "none";
        }
    });
})();
