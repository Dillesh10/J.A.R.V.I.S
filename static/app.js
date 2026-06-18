// State variables
let appState = "IDLE"; // IDLE, LISTENING, THINKING, SPEAKING
let audioContext = null;
let analyser = null;
let micStream = null;
let dataArray = null;
let recentLogCount = 0;

// Speech Recognition (Browser STT)
const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
let recognition = null;
if (SpeechRecognition) {
    recognition = new SpeechRecognition();
    recognition.continuous = false;
    recognition.interimResults = false;
    recognition.lang = 'en-US';
}

// Elements
const systemTimeEl = document.getElementById('system-time');
const statOsEl = document.getElementById('stat-os');
const statHostnameEl = document.getElementById('stat-hostname');
const statHardwareEl = document.getElementById('stat-hardware');
const statTimezoneEl = document.getElementById('stat-timezone');
const statUptimeEl = document.getElementById('stat-uptime');
const memoryListEl = document.getElementById('memory-list');
const logTerminalEl = document.getElementById('log-terminal');
const chatMessagesEl = document.getElementById('chat-messages');
const textInputEl = document.getElementById('text-input');
const sendBtnEl = document.getElementById('send-btn');
const micBtnEl = document.getElementById('mic-btn');
const voiceFeedbackEl = document.getElementById('voice-feedback');
const voiceSelectEl = document.getElementById('voice-select');
const voiceOutputToggleEl = document.getElementById('voice-output-toggle');
const reactorStateTextEl = document.getElementById('reactor-state-text');
const canvas = document.getElementById('reactor-canvas');
const ctx = canvas.getContext('2d');

// Agent Registry Elements
const agentRouterEl = document.getElementById('agent-router');
const agentResearcherEl = document.getElementById('agent-researcher');
const agentCoderEl = document.getElementById('agent-coder');

// 1. Clock and Time Updater
function updateClock() {
    const now = new Date();
    systemTimeEl.textContent = now.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' });
}
setInterval(updateClock, 1000);
updateClock();

// 2. Fetch System Info (Run once on load)
async function fetchSystemInfo() {
    try {
        const response = await fetch('/api/system_info');
        const data = await response.json();
        
        // Populate DOM
        statOsEl.textContent = data.os || "Windows 11";
        statHostnameEl.textContent = data.hostname || "localhost";
        statHardwareEl.textContent = data.hardware || "x86_64";
        statTimezoneEl.textContent = data.timezone || "Local System";
        
        // Calculate dynamic session time
        let seconds = 0;
        setInterval(() => {
            seconds++;
            const hrs = String(Math.floor(seconds / 3600)).padStart(2, '0');
            const mins = String(Math.floor((seconds % 3600) / 60)).padStart(2, '0');
            const secs = String(seconds % 60).padStart(2, '0');
            statUptimeEl.textContent = `${hrs}:${mins}:${secs}`;
        }, 1000);

    } catch (err) {
        console.error("Error fetching system info:", err);
    }
}
fetchSystemInfo();

// 3. Audio & Voice Synthesizer Setup (Browser TTS)
let systemVoices = [];
function populateVoices() {
    if (typeof speechSynthesis === 'undefined') return;
    systemVoices = speechSynthesis.getVoices();
    voiceSelectEl.innerHTML = '';
    
    // Prioritize English voices or specifically male/robotic sounding ones
    let jarvisVoice = systemVoices.find(v => v.name.includes("David") || v.name.includes("Zira") || v.name.includes("Google US English"));
    
    systemVoices.forEach((voice, i) => {
        const option = document.createElement('option');
        option.value = voice.name;
        option.textContent = `${voice.name} (${voice.lang})`;
        if (jarvisVoice && voice.name === jarvisVoice.name) {
            option.selected = true;
        }
        voiceSelectEl.appendChild(option);
    });
}
populateVoices();
if (typeof speechSynthesis !== 'undefined' && speechSynthesis.onvoiceschanged !== undefined) {
    speechSynthesis.onvoiceschanged = populateVoices;
}

function speakText(text) {
    if (!voiceOutputToggleEl.checked) return;
    if (typeof speechSynthesis === 'undefined') return;

    // Cancel any ongoing speech
    speechSynthesis.cancel();

    const utterance = new SpeechSynthesisUtterance(text);
    
    // Set selected voice
    const selectedVoiceName = voiceSelectEl.value;
    if (selectedVoiceName) {
        const voice = systemVoices.find(v => v.name === selectedVoiceName);
        if (voice) utterance.voice = voice;
    }
    
    utterance.rate = 1.05; // Slightly faster for slicker delivery
    utterance.pitch = 0.95; // Slightly lower pitch for cooler tone

    utterance.onstart = () => {
        setReactorState("SPEAKING");
        voiceFeedbackEl.textContent = "Speaking...";
    };

    utterance.onend = () => {
        setReactorState("IDLE");
        voiceFeedbackEl.textContent = "Ready, sir.";
    };

    utterance.onerror = () => {
        setReactorState("IDLE");
        voiceFeedbackEl.textContent = "Speech synthesis error, sir.";
    };

    speechSynthesis.speak(utterance);
}

// 4. Set App State
function setReactorState(state) {
    appState = state;
    reactorStateTextEl.textContent = state;
    
    // Update visualizer color palette and rotation styles in canvas loop
    if (state === "IDLE") {
        voiceFeedbackEl.textContent = "Ready for command, sir.";
        resetActiveAgents();
    } else if (state === "LISTENING") {
        voiceFeedbackEl.textContent = "Listening to microphone...";
    } else if (state === "THINKING") {
        voiceFeedbackEl.textContent = "Processing core dispatch...";
    }
}

function resetActiveAgents() {
    agentRouterEl.className = "agent-card active";
    agentResearcherEl.className = "agent-card";
    agentCoderEl.className = "agent-card";
}

// 5. Speech Recognition Event Handlers (Browser STT)
if (recognition) {
    recognition.onstart = () => {
        setReactorState("LISTENING");
        micBtnEl.classList.add('listening');
        initMicAudioContext(); // Enable real-time microphone visualizer
    };

    recognition.onerror = (event) => {
        console.error("Speech recognition error:", event.error);
        setReactorState("IDLE");
        micBtnEl.classList.remove('listening');
        voiceFeedbackEl.textContent = `Speech error: ${event.error}`;
        stopMicStream();
    };

    recognition.onend = () => {
        micBtnEl.classList.remove('listening');
        if (appState === "LISTENING") {
            setReactorState("IDLE");
        }
        stopMicStream();
    };

    recognition.onresult = (event) => {
        const transcript = event.results[0][0].transcript;
        voiceFeedbackEl.textContent = `Heard: "${transcript}"`;
        // Send user input to chat
        sendUserMessage(transcript);
    };
}

// Microphone audio-capture for Canvas Visualizer
async function initMicAudioContext() {
    try {
        if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) return;
        
        micStream = await navigator.mediaDevices.getUserMedia({ audio: true });
        
        audioContext = new (window.AudioContext || window.webkitAudioContext)();
        analyser = audioContext.createAnalyser();
        analyser.fftSize = 256;
        
        const source = audioContext.createMediaStreamSource(micStream);
        source.connect(analyser);
        
        const bufferLength = analyser.frequencyBinCount;
        dataArray = new Uint8Array(bufferLength);
    } catch (err) {
        console.warn("Unable to capture microphone for audio visualization:", err);
    }
}

function stopMicStream() {
    if (micStream) {
        micStream.getTracks().forEach(track => track.stop());
        micStream = null;
    }
    if (audioContext) {
        audioContext.close();
        audioContext = null;
        analyser = null;
    }
    dataArray = null;
}

// Toggle voice input
micBtnEl.addEventListener('click', () => {
    if (!recognition) {
        alert("Web Speech Recognition is not supported by your browser. Please try Google Chrome, sir.");
        return;
    }
    if (appState === "LISTENING") {
        recognition.stop();
    } else {
        // Cancel speech if speaking
        if (speechSynthesis && speechSynthesis.speaking) {
            speechSynthesis.cancel();
        }
        recognition.start();
    }
});

// 6. Send message to backend
async function sendUserMessage(text) {
    if (!text.trim()) return;
    
    // Add user message to UI chat log
    appendChatMessage("YOU", text, "user-message");
    textInputEl.value = "";
    
    setReactorState("THINKING");
    
    try {
        const response = await fetch('/api/chat', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ message: text })
        });
        
        if (!response.ok) {
            let errorMsg = "I encountered an error processing your request, sir.";
            try {
                const data = await response.json();
                errorMsg = data.detail || data.error || errorMsg;
            } catch (jsonErr) {
                // Not JSON
            }
            appendChatMessage("SYSTEM ERROR", errorMsg, "system");
            setReactorState("IDLE");
            speakText("An error occurred, sir.");
            return;
        }
        
        const data = await response.json();
        
        if (data.response) {
            // Check for special OPEN_URL directive
            if (data.response.startsWith('OPEN_URL:')) {
                const url = data.response.substring('OPEN_URL:'.length);
                // Provide a clickable link for the user
                const linkHtml = `<a href="${url}" target="_blank" rel="noopener noreferrer">Open ${url}</a>`;
                appendChatMessage('SYSTEM', linkHtml, 'system');
                // Attempt to open programmatically as a fallback (may be blocked)
                try {
                    const a = document.createElement('a');
                    a.href = url;
                    a.target = '_blank';
                    a.rel = 'noopener noreferrer';
                    document.body.appendChild(a);
                    a.click();
                    document.body.removeChild(a);
                } catch (e) { console.warn('Failed to open URL programmatically', e); }
            } else {
                // Regular JARVIS response
                appendChatMessage("J.A.R.V.I.S.", data.response, "jarvis-message");
                // Speak response out loud
                speakText(data.response);
            }
        } else {
            appendChatMessage("SYSTEM ERROR", "Empty response from server, sir.", "system");
            speakText("I received an empty response, sir.");
        }
        
        // Ensure state returns to IDLE if TTS is disabled or finished
        if (!voiceOutputToggleEl.checked) {
            setReactorState("IDLE");
        }
        
    } catch (err) {
        appendChatMessage("SYSTEM ERROR", "Unable to communicate with local JARVIS router server.", "system");
        setReactorState("IDLE");
        speakText("I encountered an API link issue, sir.");
    }
}

// Send via click
sendBtnEl.addEventListener('click', () => {
    sendUserMessage(textInputEl.value);
});

// Send via Enter key
textInputEl.addEventListener('keypress', (e) => {
    if (e.key === 'Enter') {
        sendUserMessage(textInputEl.value);
    }
});

// Helper to append message to Chat Container
        // Append message to chat UI
        const msgDiv = document.createElement('div');
        msgDiv.className = `message ${cssClass}`;
        
        const authorDiv = document.createElement('div');
        authorDiv.className = 'msg-author';
        authorDiv.textContent = sender;
        
        const textDiv = document.createElement('div');
        textDiv.className = 'msg-text';
        // Render HTML for system messages (e.g., clickable links)
        if (cssClass === 'system') {
            textDiv.innerHTML = text;
        } else {
            textDiv.textContent = text;
        }
        
        msgDiv.appendChild(authorDiv);
        msgDiv.appendChild(textDiv);
        
        chatMessagesEl.appendChild(msgDiv);
        chatMessagesEl.scrollTop = chatMessagesEl.scrollHeight;

// 7. Polling logs & memory bank (1.5 seconds)
async function pollLogsAndMemory() {
    try {
        // Poll Logs
        const logRes = await fetch('/api/logs');
        const logs = await logRes.json();
        
        if (logs && logs.length > 0) {
            logs.forEach(log => {
                const logDiv = document.createElement('div');
                const catClass = log.category.toLowerCase();
                logDiv.className = `log-entry ${catClass}`;
                
                logDiv.innerHTML = `<span class="log-time">[${log.timestamp}]</span> <span class="log-tag">${log.category}</span>: ${escapeHTML(log.message)}`;
                logTerminalEl.appendChild(logDiv);
                
                // Track active sub-agents from logs
                updateActiveAgentsFromLog(log);
            });
            logTerminalEl.scrollTop = logTerminalEl.scrollHeight;
        }

        // Poll Memory facts
        const memRes = await fetch('/api/memory');
        const memory = await memRes.json();
        
        if (memory && memory.facts && memory.facts.length > 0 && memory.facts[0] !== "No shared facts available.") {
            memoryListEl.innerHTML = '';
            memory.facts.forEach(fact => {
                const li = document.createElement('li');
                li.textContent = fact;
                memoryListEl.appendChild(li);
            });
        } else {
            memoryListEl.innerHTML = '<li class="empty-state">No facts stored in memory yet, sir.</li>';
        }

    } catch (err) {
        console.warn("Polling error:", err);
    }
}
setInterval(pollLogsAndMemory, 1500);
pollLogsAndMemory(); // Run immediately

function updateActiveAgentsFromLog(log) {
    const msg = log.message.toLowerCase();
    
    if (msg.includes("delegating task to the researcher")) {
        agentRouterEl.className = "agent-card active";
        agentResearcherEl.className = "agent-card active-working";
        agentCoderEl.className = "agent-card";
    } else if (msg.includes("delegating task to the coder")) {
        agentRouterEl.className = "agent-card active";
        agentResearcherEl.className = "agent-card";
        agentCoderEl.className = "agent-card active-working";
    } else if (msg.includes("task completed") || msg.includes("system secure")) {
        resetActiveAgents();
    }
}

function escapeHTML(str) {
    return str.replace(/[&<>'"]/g, 
        tag => ({
            '&': '&amp;',
            '<': '&lt;',
            '>': '&gt;',
            "'": '&#39;',
            '"': '&quot;'
        }[tag] || tag)
    );
}

// 8. Dynamic Arc Reactor Canvas Visualization Loop
let rotationAngle = 0;

function drawReactor() {
    const width = canvas.width;
    const height = canvas.height;
    const centerX = width / 2;
    const centerY = height / 2;
    
    // Clear canvas
    ctx.clearRect(0, 0, width, height);
    
    // Adjust colors and speed based on state
    let primaryColor = "#00f0ff"; // Cyan
    let secondaryColor = "rgba(0, 240, 255, 0.2)";
    let spinSpeed = 0.005;
    
    if (appState === "LISTENING") {
        primaryColor = "#00ff66"; // Green
        secondaryColor = "rgba(0, 255, 102, 0.15)";
        spinSpeed = 0.01;
    } else if (appState === "THINKING") {
        primaryColor = "#ffaa00"; // Amber/Orange
        secondaryColor = "rgba(255, 170, 0, 0.15)";
        spinSpeed = 0.025;
    } else if (appState === "SPEAKING") {
        primaryColor = "#00f0ff";
        secondaryColor = "rgba(0, 240, 255, 0.2)";
        spinSpeed = 0.008;
    }
    
    rotationAngle += spinSpeed;
    
    // Draw Outer glowing rings
    ctx.strokeStyle = secondaryColor;
    ctx.lineWidth = 1;
    
    ctx.beginPath();
    ctx.arc(centerX, centerY, 100, 0, Math.PI * 2);
    ctx.stroke();
    
    ctx.beginPath();
    ctx.arc(centerX, centerY, 90, 0, Math.PI * 2);
    ctx.stroke();

    // Draw rotating segment ring
    ctx.save();
    ctx.translate(centerX, centerY);
    ctx.rotate(rotationAngle);
    
    ctx.strokeStyle = primaryColor;
    ctx.lineWidth = 3;
    ctx.shadowBlur = 10;
    ctx.shadowColor = primaryColor;
    
    // 3 segments
    for (let i = 0; i < 3; i++) {
        ctx.beginPath();
        ctx.arc(0, 0, 80, (i * Math.PI * 2 / 3), (i * Math.PI * 2 / 3) + Math.PI / 3);
        ctx.stroke();
    }
    
    // Draw smaller dashes ring rotating in opposite direction
    ctx.restore();
    ctx.save();
    ctx.translate(centerX, centerY);
    ctx.rotate(-rotationAngle * 1.5);
    ctx.strokeStyle = primaryColor;
    ctx.lineWidth = 1.5;
    ctx.setLineDash([4, 12]);
    ctx.beginPath();
    ctx.arc(0, 0, 68, 0, Math.PI * 2);
    ctx.stroke();
    ctx.setLineDash([]); // Reset
    ctx.restore();

    // Center Core Glow
    ctx.shadowBlur = 15;
    ctx.shadowColor = primaryColor;
    ctx.fillStyle = primaryColor;
    ctx.beginPath();
    ctx.arc(centerX, centerY, 22, 0, Math.PI * 2);
    ctx.fill();
    
    // Core ring
    ctx.shadowBlur = 0;
    ctx.strokeStyle = "#ffffff";
    ctx.lineWidth = 1.5;
    ctx.beginPath();
    ctx.arc(centerX, centerY, 26, 0, Math.PI * 2);
    ctx.stroke();
    
    // Draw audio waveform depending on state
    if (appState === "LISTENING" && dataArray) {
        // Read real microphone analyzer values
        analyser.getByteFrequencyData(dataArray);
        ctx.strokeStyle = primaryColor;
        ctx.lineWidth = 2;
        ctx.shadowBlur = 5;
        ctx.shadowColor = primaryColor;
        
        ctx.beginPath();
        const totalPoints = 32;
        for (let i = 0; i < totalPoints; i++) {
            const angle = (i / totalPoints) * Math.PI * 2;
            const value = dataArray[i % dataArray.length] / 255.0; // scale 0 to 1
            const r = 40 + (value * 22);
            const x = centerX + Math.cos(angle) * r;
            const y = centerY + Math.sin(angle) * r;
            if (i === 0) {
                ctx.moveTo(x, y);
            } else {
                ctx.lineTo(x, y);
            }
        }
        ctx.closePath();
        ctx.stroke();
        
    } else if (appState === "SPEAKING") {
        // Generate simulated voice waves
        ctx.strokeStyle = primaryColor;
        ctx.lineWidth = 2.5;
        ctx.shadowBlur = 8;
        ctx.shadowColor = primaryColor;
        
        ctx.beginPath();
        const totalPoints = 40;
        const timeFactor = Date.now() * 0.01;
        for (let i = 0; i < totalPoints; i++) {
            const angle = (i / totalPoints) * Math.PI * 2;
            // Pulsing sine wave simulation
            const value = 0.5 + 0.5 * Math.sin(angle * 4 + timeFactor) * Math.cos(angle * 2 + timeFactor * 0.5);
            const r = 40 + (value * 18);
            const x = centerX + Math.cos(angle) * r;
            const y = centerY + Math.sin(angle) * r;
            if (i === 0) {
                ctx.moveTo(x, y);
            } else {
                ctx.lineTo(x, y);
            }
        }
        ctx.closePath();
        ctx.stroke();
    } else if (appState === "THINKING") {
        // Pulsing rings around the center core
        ctx.strokeStyle = primaryColor;
        ctx.lineWidth = 1.5;
        ctx.shadowBlur = 8;
        ctx.shadowColor = primaryColor;
        const scale = 1.0 + 0.15 * Math.sin(Date.now() * 0.01);
        ctx.beginPath();
        ctx.arc(centerX, centerY, 42 * scale, 0, Math.PI * 2);
        ctx.stroke();
    } else {
        // Idle subtle expanding circle
        ctx.strokeStyle = "rgba(0, 240, 255, 0.4)";
        ctx.lineWidth = 1;
        const scale = 1.0 + 0.05 * Math.sin(Date.now() * 0.002);
        ctx.beginPath();
        ctx.arc(centerX, centerY, 45 * scale, 0, Math.PI * 2);
        ctx.stroke();
    }
    
    requestAnimationFrame(drawReactor);
}
drawReactor();
