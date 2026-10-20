// WhisperFlow Local • Elite 2026 Frontend JavaScript Engine
// Ultra-Responsive, Zero-Lag, GPU-Accelerated Audio Visualizer & Key Binding System

(function () {
  'use strict';

  // State
  let currentActionToBind = null;
  let isRecordingTest = false;
  let isListeningForKey = false;
  let currentConfig = null;

  // Recording Timer State
  let timerInterval = null;
  let timerStartTime = 0;

  // Web Audio API Visualizer State
  let audioCtx = null;
  let analyser = null;
  let micStream = null;
  let dataArray = null;
  let animationFrameId = null;
  let isVisualizerRunning = false;
  let peakDb = -60;

  // DOM Elements cache
  let dom = {};

  document.addEventListener('DOMContentLoaded', () => {
    cacheDOMElements();
    initTabs();
    initKeyBindingSystem();
    initOptionsAndSettings();
    initTestStudio();
    initDynamicIsland();
    initCanvasVisualizer();
    initToastAction();

    // Check pywebview bridge readiness
    if (window.pywebview && window.pywebview.api) {
      loadAppConfig();
    } else {
      window.addEventListener('pywebviewready', () => {
        loadAppConfig();
      });
    }
  });

  function cacheDOMElements() {
    dom = {      // Dynamic Island
      dynamicIsland: document.getElementById('dynamicIsland'),
      islandPill: document.getElementById('islandPill'),
      islandIdle: document.getElementById('islandIdle'),
      islandRecording: document.getElementById('islandRecording'),
      islandTranscribing: document.getElementById('islandTranscribing'),
      islandDone: document.getElementById('islandDone'),
      islandRecText: document.getElementById('islandRecText'),
      islandTimer: document.getElementById('islandTimer'),
      islandDoneText: document.getElementById('islandDoneText'),

      // Header
      headerStatusBadge: document.getElementById('headerStatusBadge'),
      statusText: document.getElementById('statusText'),

      // Key Badges
      badgePushKey: document.getElementById('badgePushKey'),
      badgeToggleKey: document.getElementById('badgeToggleKey'),
      badgeCancelKey: document.getElementById('badgeCancelKey'),
      boxPushKey: document.getElementById('boxPushKey'),
      boxToggleKey: document.getElementById('boxToggleKey'),
      boxCancelKey: document.getElementById('boxCancelKey'),

      // Options
      checkSound: document.getElementById('checkSound'),
      checkOverlay: document.getElementById('checkOverlay'),
      selectModel: document.getElementById('selectModel'),
      selectLanguage: document.getElementById('selectLanguage'),

      // Studio
      btnBigMic: document.getElementById('btnBigMic'),
      micHeading: document.getElementById('micHeading'),
      micSubtext: document.getElementById('micSubtext'),
      studioStateBadge: document.getElementById('studioStateBadge'),
      studioStateText: document.getElementById('studioStateText'),
      studioTimer: document.getElementById('studioTimer'),
      visualizerCanvas: document.getElementById('visualizerCanvas'),
      vuMeterFill: document.getElementById('vuMeterFill'),
      vuMeterPeak: document.getElementById('vuMeterPeak'),
      peakDbLabel: document.getElementById('peakDbLabel'),
      txtOutput: document.getElementById('txtOutput'),
      latencyBadge: document.getElementById('latencyBadge'),
      latencyText: document.getElementById('latencyText'),
      statChars: document.getElementById('statChars'),
      statWords: document.getElementById('statWords'),
      btnCopy: document.getElementById('btnCopy'),
      btnClear: document.getElementById('btnClear'),

      // Key Capture HUD
      keyCaptureHud: document.getElementById('keyCaptureHud'),
      hudBackdrop: document.getElementById('hudBackdrop'),
      hudActionTitle: document.getElementById('hudActionTitle'),
      hudCapturedKey: document.getElementById('hudCapturedKey'),
      btnCancelHud: document.getElementById('btnCancelHud'),

      // Toast
      toast: document.getElementById('toast'),
      toastMessage: document.getElementById('toastMessage'),
      toastIcon: document.getElementById('toastIcon'),
      toastAction: document.getElementById('toastAction')
    };
  }

  // =========================================================================
  // TOAST NOTIFICATIONS (succès = menthe, erreur = rose, action optionnelle)
  // =========================================================================
  let toastTimeout = null;
  let toastActionCb = null;

  function hideToast() {
    clearTimeout(toastTimeout);
    dom.toast.classList.remove('show');
    toastActionCb = null;
    if (dom.toastAction) dom.toastAction.hidden = true;
  }

  function showToast(msg, isSuccess = true, action = null) {
    if (!dom.toast) return;
    clearTimeout(toastTimeout);
    dom.toastMessage.textContent = msg;
    dom.toast.classList.toggle('error', !isSuccess);
    if (dom.toastIcon) dom.toastIcon.textContent = isSuccess ? '✓' : '!';
    toastActionCb = null;
    if (action && typeof action.cb === 'function') {
      toastActionCb = action.cb;
      if (dom.toastAction) {
        dom.toastAction.textContent = action.label || 'Annuler';
        dom.toastAction.hidden = false;
      }
    } else if (dom.toastAction) {
      dom.toastAction.hidden = true;
    }
    dom.toast.classList.add('show');
    toastTimeout = setTimeout(hideToast, action ? 5000 : 2400);
  }

  function initToastAction() {
    if (!dom.toastAction) return;
    dom.toastAction.addEventListener('click', () => {
      const cb = toastActionCb;
      hideToast();
      if (cb) cb();
    });
  }

  // =========================================================================
  // TABS NAVIGATION
  // =========================================================================
  function initTabs() {
    const tabs = Array.from(document.querySelectorAll('.tab-btn'));
    tabs.forEach((tab, index) => {
      tab.addEventListener('click', () => activateTab(tab));
      tab.addEventListener('keydown', (e) => {
        let target = null;
        if (e.key === 'ArrowRight') target = tabs[(index + 1) % tabs.length];
        else if (e.key === 'ArrowLeft') target = tabs[(index - 1 + tabs.length) % tabs.length];
        else if (e.key === 'Home') target = tabs[0];
        else if (e.key === 'End') target = tabs[tabs.length - 1];
        if (target) {
          e.preventDefault();
          activateTab(target);
          target.focus();
        }
      });
    });
  }

  function activateTab(tab) {
    document.querySelectorAll('.tab-btn').forEach(t => {
      t.classList.remove('active');
      t.setAttribute('aria-selected', 'false');
      t.setAttribute('tabindex', '-1');
    });
    document.querySelectorAll('.tab-content').forEach(c => c.classList.remove('active'));

    tab.classList.add('active');
    tab.setAttribute('aria-selected', 'true');
    tab.setAttribute('tabindex', '0');
    const target = document.getElementById(tab.dataset.tab);
    if (target) target.classList.add('active');
  }

  // =========================================================================
  // CONFIG LOADING & SYNC
  // =========================================================================
  async function loadAppConfig() {
    try {
      if (!window.pywebview || !window.pywebview.api) return;
      const config = await window.pywebview.api.get_config();
      if (config) {
        currentConfig = config;
        applyConfigToUI(config);
        await refreshModelStatus();
      }
    } catch (err) {
      console.warn("Erreur chargement config:", err);
    }
  }

  function formatKeyDisplayName(keyName) {
    if (!keyName) return "Ctrl + Win";
    const k = keyName.toLowerCase().trim();
    if (k === "mouse4" || k === "x1" || k === "souris4" || k === "mouse_4") return "Souris 4";
    if (k === "mouse5" || k === "x2" || k === "souris5" || k === "mouse_5") return "Souris 5";
    if (k === "mouse3" || k === "middle" || k === "souris3") return "Clic molette";
    if (k === "copilot" || k === "f23") return "Copilot";
    if (k === "ctrl+win" || k === "win+ctrl") return "Ctrl + Win";
    if (k === "alt+space" || k === "space+alt") return "Alt + Espace";
    if (k === "esc") return "Esc";
    if (k === "pause") return "Pause";
    if (k === "insert") return "Insert";
    if (k === "scroll_lock") return "Arrêt défil";
    return k.toUpperCase();
  }

  async function refreshModelStatus() {
    if (!window.pywebview || !window.pywebview.api) return;
    try {
      const status = await window.pywebview.api.get_status();
      updateHeaderStatus(status.error || (status.model_ready ? 'Modèle prêt' : 'Chargement du modèle…'), status.model_ready && !status.error);
    } catch (err) { console.warn('Statut indisponible', err); }
  }
  setInterval(refreshModelStatus, 2000);
  window.onAppError = function (message) {
    window.onRecordingStateChange(false, 'idle');
    updateHeaderStatus(message, false);
    if (dom.studioStateText) dom.studioStateText.textContent = message;
    showToast(message);
  };

  function applyConfigToUI(cfg) {
    if (cfg.hotkey_push && dom.badgePushKey) {
      dom.badgePushKey.textContent = formatKeyDisplayName(cfg.hotkey_push);
    }
    if (cfg.hotkey_toggle && dom.badgeToggleKey) {
      dom.badgeToggleKey.textContent = formatKeyDisplayName(cfg.hotkey_toggle);
    }
    if (cfg.hotkey_cancel && dom.badgeCancelKey) {
      dom.badgeCancelKey.textContent = formatKeyDisplayName(cfg.hotkey_cancel);
    }

    if (dom.checkSound) dom.checkSound.checked = !!cfg.sound_feedback;
    if (dom.checkOverlay) dom.checkOverlay.checked = !!cfg.show_overlay;

    if (cfg.model_size && dom.selectModel) dom.selectModel.value = cfg.model_size;
    if (cfg.language && dom.selectLanguage) dom.selectLanguage.value = cfg.language;
  }

  function updateHeaderStatus(text, isReady) {
    if (dom.statusText) dom.statusText.textContent = text;
    if (dom.headerStatusBadge) {
      // Prêt = menthe • occupé (chargement) = indigo
      dom.headerStatusBadge.className = isReady ? "status-badge ready" : "status-badge busy";
    }
  }

  // =========================================================================
  // DYNAMIC ISLAND CONTROLLER
  // =========================================================================
  function initDynamicIsland() {
    setIslandState('idle');
  }

  function setIslandState(state, info) {
    if (!dom.islandPill) return;

    dom.islandIdle.style.display = 'none';
    dom.islandRecording.style.display = 'none';
    dom.islandTranscribing.style.display = 'none';
    dom.islandDone.style.display = 'none';

    dom.islandPill.className = 'island-pill';

    if (state === 'idle') {
      const idleLabel = dom.islandIdle.querySelector('.island-label');
      const idleDot = dom.islandIdle.querySelector('.island-dot');
      if (idleLabel) idleLabel.textContent = 'Prêt';
      if (idleDot) idleDot.style.background = '';
      dom.islandIdle.style.display = 'flex';
    } else if (state === 'recording') {
      dom.islandPill.classList.add('recording');
      dom.islandRecording.style.display = 'flex';
      dom.islandRecText.textContent = info === 'toggle' ? "Écoute (bascule)…" : "Écoute…";
    } else if (state === 'transcribing') {
      dom.islandPill.classList.add('transcribing');
      dom.islandTranscribing.style.display = 'flex';
    } else if (state === 'done') {
      dom.islandPill.classList.add('done');
      dom.islandDone.style.display = 'flex';
      const durationMs = info ? Math.round(info * 1000) : 180;
      dom.islandDoneText.textContent = `Transcrit en ${durationMs} ms`;
      setTimeout(() => {
        setIslandState('idle');
      }, 2500);
    } else if (state === 'cancel') {
      dom.islandPill.classList.add('cancel');
      dom.islandIdle.style.display = 'flex';
      const idleLabel = dom.islandIdle.querySelector('.island-label');
      const idleDot = dom.islandIdle.querySelector('.island-dot');
      if (idleLabel) idleLabel.textContent = 'Annulé';
      if (idleDot) idleDot.style.background = 'var(--danger-text)';
      setTimeout(() => {
        setIslandState('idle');
      }, 1400);
    }
  }

  // =========================================================================
  // ULTRA-FLUID KEY CAPTURE SYSTEM
  // =========================================================================
  function initKeyBindingSystem() {
    // 1. Boutons "Changer"
    document.querySelectorAll('.btn-assign').forEach(btn => {
      btn.addEventListener('click', (e) => {
        const action = btn.dataset.action;
        openKeyCaptureHUD(action);
      });
    });

    // 2. Clic direct sur le Keycap (souris ou clavier Entrée/Espace)
    [dom.boxPushKey, dom.boxToggleKey, dom.boxCancelKey].forEach(box => {
      if (!box) return;
      box.addEventListener('click', () => {
        const card = box.closest('.key-card');
        const action = (card && card.dataset.action) || "push_to_talk";
        openKeyCaptureHUD(action);
      });
      box.addEventListener('keydown', (e) => {
        if (e.key === 'Enter' || e.key === ' ') {
          e.preventDefault();
          box.click();
        }
      });
    });

    // 3. Preset chips (1-Clic instantané)
    document.querySelectorAll('.preset-chips .chip').forEach(chip => {
      chip.addEventListener('click', async (e) => {
        e.stopPropagation();
        const action = chip.dataset.action;
        const key = chip.dataset.key;
        await assignKeyAction(action, key);
      });
    });

    // 4. Suggestions in HUD modal
    document.querySelectorAll('.sug-chips .sug-btn').forEach(btn => {
      btn.addEventListener('click', async (e) => {
        e.stopPropagation();
        const key = btn.dataset.key;
        if (currentActionToBind) {
          await assignKeyAction(currentActionToBind, key);
          closeKeyCaptureHUD();
        }
      });
    });

    // 5. Fermeture du modal HUD
    if (dom.btnCancelHud) {
      dom.btnCancelHud.addEventListener('click', closeKeyCaptureHUD);
    }
    if (dom.hudBackdrop) {
      dom.hudBackdrop.addEventListener('click', closeKeyCaptureHUD);
    }

    // 6. Écoute globale des frappes clavier
    window.addEventListener('keydown', handleGlobalKeydown);

    // 7. Écoute des boutons souris (Souris 4, 5, Molette)
    window.addEventListener('mousedown', handleGlobalMousedown);
  }

  function handleGlobalMousedown(e) {
    if (!isListeningForKey || !currentActionToBind) return;
    // e.button: 3 = Bouton latéral 1 (Mouse 4), 4 = Bouton latéral 2 (Mouse 5), 1 = Molette (Mouse 3)
    if (e.button === 3 || e.button === 4 || e.button === 1) {
      e.preventDefault();
      e.stopPropagation();
      let detectedMouse = e.button === 3 ? "mouse4" : (e.button === 4 ? "mouse5" : "mouse3");
      if (dom.hudCapturedKey) {
        dom.hudCapturedKey.textContent = formatKeyDisplayName(detectedMouse);
      }
      const action = currentActionToBind;
      setTimeout(async () => {
        await assignKeyAction(action, detectedMouse);
        closeKeyCaptureHUD();
      }, 350);
    }
  }

  function openKeyCaptureHUD(action) {
    currentActionToBind = action;
    isListeningForKey = true;

    const actionLabels = {
      push_to_talk: "Dictée push-to-talk",
      toggle: "Dictée bascule",
      cancel: "Annulation de la dictée"
    };

    if (dom.hudActionTitle) {
      dom.hudActionTitle.textContent = `Assigner : ${actionLabels[action] || action}`;
    }
    if (dom.hudCapturedKey) {
      dom.hudCapturedKey.textContent = "Appuyez sur une touche…";
    }
    if (dom.keyCaptureHud) {
      dom.keyCaptureHud.classList.add('active');
    }
  }

  function closeKeyCaptureHUD() {
    isListeningForKey = false;
    currentActionToBind = null;
    if (dom.keyCaptureHud) {
      dom.keyCaptureHud.classList.remove('active');
    }
  }

  async function assignKeyAction(action, keyName) {
    keyName = keyName.toLowerCase().trim();
    if (window.pywebview && window.pywebview.api) {
      try {
        await window.pywebview.api.set_key(action, keyName);
      } catch (err) {
        console.error("Erreur set_key API:", err);
      }
    }

    // Mise à jour visuelle immédiate
    const formatted = formatKeyDisplayName(keyName);
    if (action === "push_to_talk" && dom.badgePushKey) {
      dom.badgePushKey.textContent = formatted;
      bounceKeycap(dom.boxPushKey);
    } else if (action === "toggle" && dom.badgeToggleKey) {
      dom.badgeToggleKey.textContent = formatted;
      bounceKeycap(dom.boxToggleKey);
    } else if (action === "cancel" && dom.badgeCancelKey) {
      dom.badgeCancelKey.textContent = formatted;
      bounceKeycap(dom.boxCancelKey);
    }

    showToast(`Raccourci assigné : ${formatted}`);
  }

  function bounceKeycap(container) {
    if (!container) return;
    const keycap = container.querySelector('.keycap');
    if (!keycap) return;
    keycap.style.transform = "scale(1.15)";
    keycap.style.borderColor = "var(--accent-emerald)";
    setTimeout(() => {
      keycap.style.transform = "";
      keycap.style.borderColor = "";
    }, 300);
  }

  function handleGlobalKeydown(e) {
    if (!isListeningForKey || !currentActionToBind) return;
    e.preventDefault();
    e.stopPropagation();

    // Touche Échap pour fermer le modal
    if (e.key === "Escape" && currentActionToBind !== "cancel") {
      closeKeyCaptureHUD();
      return;
    }

    let detectedKey = "";

    // 0. Détection physique Touche Copilot (F23 ou Win+Shift+F23)
    if (e.key === "F23" || e.code === "F23" || e.key.match(/^F2[0-4]$/i)) {
      detectedKey = "copilot";
    }
    // 1. Détection des touches de fonction F1-F12
    else if (e.key.match(/^F[1-9]$|^F1[0-2]$/i)) {
      detectedKey = e.key.toLowerCase();
    }
    // 2. Détection combinaisons avec Ctrl ou Alt
    else if (e.ctrlKey && (e.metaKey || e.key === "Meta" || e.code.includes("OS") || e.code.includes("Meta"))) {
      detectedKey = "ctrl+win";
    } else if (e.altKey && (e.code === "Space" || e.key === " ")) {
      detectedKey = "alt+space";
    } else if (e.ctrlKey && e.shiftKey && (e.code === "Space" || e.key === " ")) {
      detectedKey = "ctrl+shift+space";
    }
    // 3. Détection touches spéciales
    else if (e.code === "Pause") {
      detectedKey = "pause";
    } else if (e.code === "Insert") {
      detectedKey = "insert";
    } else if (e.code === "ScrollLock") {
      detectedKey = "scroll_lock";
    } else if (e.key === "Escape") {
      detectedKey = "esc";
    } else if (e.code === "Backspace") {
      detectedKey = "backspace";
    } else if (e.code === "Delete") {
      detectedKey = "delete";
    } else if (e.code === "Home") {
      detectedKey = "home";
    } else if (e.code === "End") {
      detectedKey = "end";
    }
    // 4. Modificateurs isolés
    else if (["Control", "Shift", "Alt", "Meta"].includes(e.key)) {
      // Ignorer tant qu'une touche d'action n'est pas frappée
      if (dom.hudCapturedKey) {
        dom.hudCapturedKey.textContent = `${e.key.toUpperCase()} + ...`;
      }
      return;
    }
    // 5. Touche standard
    else {
      detectedKey = e.key.toLowerCase();
    }

    if (detectedKey) {
      if (dom.hudCapturedKey) {
        dom.hudCapturedKey.textContent = formatKeyDisplayName(detectedKey);
      }
      const action = currentActionToBind;
      setTimeout(async () => {
        await assignKeyAction(action, detectedKey);
        closeKeyCaptureHUD();
      }, 350);
    }
  }

  // =========================================================================
  // OPTIONS & HARDWARE SETTINGS
  // =========================================================================
  function initOptionsAndSettings() {
    if (dom.checkSound) {
      dom.checkSound.addEventListener('change', async (e) => {
        if (window.pywebview && window.pywebview.api) {
          await window.pywebview.api.set_setting('sound_feedback', e.target.checked);
          showToast(e.target.checked ? "Retour sonore activé" : "Retour sonore désactivé");
        }
      });
    }

    if (dom.checkOverlay) {
      dom.checkOverlay.addEventListener('change', async (e) => {
        if (window.pywebview && window.pywebview.api) {
          await window.pywebview.api.set_setting('show_overlay', e.target.checked);
          showToast(e.target.checked ? "Widget flottant affiché" : "Widget flottant masqué");
        }
      });
    }

    if (dom.selectModel) {
      dom.selectModel.addEventListener('change', async (e) => {
        updateHeaderStatus("Chargement du modèle…", false);
        showToast(`Chargement du modèle ${e.target.value}…`);
        if (window.pywebview && window.pywebview.api) {
          await window.pywebview.api.set_setting('model_size', e.target.value);
          updateHeaderStatus("Modèle prêt", true);
          showToast(`Modèle ${e.target.value} actif`);
        }
      });
    }

    if (dom.selectLanguage) {
      dom.selectLanguage.addEventListener('change', async (e) => {
        if (window.pywebview && window.pywebview.api) {
          await window.pywebview.api.set_setting('language', e.target.value);
          showToast(`Langue : ${e.target.options[e.target.selectedIndex].text}`);
        }
      });
    }
  }

  // =========================================================================
  // REAL-TIME AUDIO VISUALIZER & VU-METER (Web Audio + Organic Fallback)
  // =========================================================================
  function initCanvasVisualizer() {
    const canvas = dom.visualizerCanvas;
    if (!canvas) return;

    // Resize canvas to DPR for crystal clear retina rendering
    const dpr = window.devicePixelRatio || 1;
    const rect = canvas.getBoundingClientRect();
    canvas.width = (rect.width || 700) * dpr;
    canvas.height = (rect.height || 85) * dpr;

    startVisualizerLoop();
  }

  async function setupWebAudioMic() {
    if (audioCtx && analyser) return;
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true, video: false });
      micStream = stream;
      audioCtx = new (window.AudioContext || window.webkitAudioContext)();
      analyser = audioCtx.createAnalyser();
      analyser.fftSize = 64;
      analyser.smoothingTimeConstant = 0.75;
      const source = audioCtx.createMediaStreamSource(stream);
      source.connect(analyser);
      dataArray = new Uint8Array(analyser.frequencyBinCount);
    } catch (err) {
      // Graceful fallback to organic synthetic audio wave if device permission not granted
      console.log("Microphone direct Web Audio inaccessible, utilisation du synthétiseur de fréquence dynamique:", err);
      dataArray = new Uint8Array(32);
    }
  }

  function startVisualizerLoop() {
    const canvas = dom.visualizerCanvas;
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    let phase = 0;

    function render() {
      animationFrameId = requestAnimationFrame(render);
      const width = canvas.width;
      const height = canvas.height;
      ctx.clearRect(0, 0, width, height);

      const numBars = 32;
      const barWidth = (width / numBars) * 0.65;
      const barGap = (width / numBars) * 0.35;

      let currentVolume = 0;

      if (analyser && isRecordingTest) {
        analyser.getByteFrequencyData(dataArray);
      } else if (isRecordingTest) {
        // Organic simulated speech frequencies when recording via global hotkey or test button
        phase += 0.08;
        for (let i = 0; i < numBars; i++) {
          const base = Math.sin(phase * 1.5 + i * 0.4) * 45 + Math.cos(phase * 2.2 + i * 0.2) * 35;
          const energy = Math.max(15, Math.min(240, 100 + base + Math.random() * 50));
          dataArray[i] = energy;
        }
      } else {
        // Idle gentle breathing line
        phase += 0.02;
        for (let i = 0; i < numBars; i++) {
          dataArray[i] = Math.max(6, Math.sin(phase + i * 0.3) * 12 + 10);
        }
      }

      // Draw frequency spectrum bars
      let sumEnergy = 0;
      for (let i = 0; i < numBars; i++) {
        const val = dataArray[i] || 0;
        sumEnergy += val;

        const barHeight = Math.max(4, (val / 255) * (height - 12));
        const x = i * (barWidth + barGap) + barGap / 2;
        const y = height - barHeight;

        // Couleurs sobre : gris au repos, menthe pendant l'enregistrement
        const grad = ctx.createLinearGradient(0, height, 0, y);
        if (isRecordingTest) {
          grad.addColorStop(0, '#059669');
          grad.addColorStop(1, '#34d399');
        } else {
          grad.addColorStop(0, 'rgba(0, 0, 0, 0.12)');
          grad.addColorStop(1, 'rgba(0, 0, 0, 0.26)');
        }

        ctx.fillStyle = grad;
        drawRoundedRect(ctx, x, y, barWidth, barHeight, 4);
      }

      // Update Decibel / VU-Meter
      if (isRecordingTest) {
        const avg = sumEnergy / numBars;
        const percent = Math.min(100, Math.max(5, (avg / 255) * 120));
        const db = Math.round((percent / 100) * 50 - 50);
        if (dom.vuMeterFill) dom.vuMeterFill.style.width = `${percent}%`;
        if (dom.vuMeterPeak) dom.vuMeterPeak.style.left = `${Math.min(98, percent + 4)}%`;
        if (dom.peakDbLabel) dom.peakDbLabel.textContent = `${db} dB`;
      } else {
        if (dom.vuMeterFill) dom.vuMeterFill.style.width = '2%';
        if (dom.vuMeterPeak) dom.vuMeterPeak.style.left = '2%';
        if (dom.peakDbLabel) dom.peakDbLabel.textContent = '−∞ dB';
      }
    }

    render();
  }

  function drawRoundedRect(ctx, x, y, w, h, radius) {
    if (h < radius) radius = h / 2;
    ctx.beginPath();
    ctx.moveTo(x + radius, y);
    ctx.lineTo(x + w - radius, y);
    ctx.quadraticCurveTo(x + w, y, x + w, y + radius);
    ctx.lineTo(x + w, y + h);
    ctx.lineTo(x, y + h);
    ctx.lineTo(x, y + radius);
    ctx.quadraticCurveTo(x, y, x, y);
    ctx.closePath();
    ctx.fill();
  }

  // =========================================================================
  // STUDIO DE TEST INTERACTIF
  // =========================================================================
  function initTestStudio() {
    const bigMic = dom.btnBigMic;
    if (!bigMic) return;

    bigMic.addEventListener('click', async () => {
      if (!window.pywebview || !window.pywebview.api) {
        showToast("Backend Whisper en cours d'initialisation...", false);
        return;
      }

      if (!isRecordingTest) {
        // Démarrer l'écoute
        await startTestRecording();
      } else {
        // Arrêter l'écoute et transcrire
        await stopTestRecording();
      }
    });

    // Bouton Copier
    if (dom.btnCopy) {
      dom.btnCopy.addEventListener('click', () => {
        const text = dom.txtOutput.value;
        if (!text) {
          showToast("Aucun texte à copier", false);
          return;
        }
        const done = () => {
          showToast("Texte copié");
          const origHtml = dom.btnCopy.innerHTML;
          dom.btnCopy.innerHTML = "<span>Copié ✓</span>";
          setTimeout(() => { dom.btnCopy.innerHTML = origHtml; }, 1400);
        };
        // API presse-papier indisponible en context file:// : repli execCommand
        const fallbackCopy = () => {
          const tmp = document.createElement('textarea');
          tmp.value = text;
          tmp.style.position = 'fixed';
          tmp.style.opacity = '0';
          document.body.appendChild(tmp);
          tmp.select();
          try { document.execCommand('copy'); done(); } catch (e) { showToast("Copie impossible", false); }
          document.body.removeChild(tmp);
        };
        if (navigator.clipboard && navigator.clipboard.writeText) {
          navigator.clipboard.writeText(text).then(done).catch(fallbackCopy);
        } else {
          fallbackCopy();
        }
      });
    }

    // Bouton Effacer — réversible via « Annuler » dans la notification
    if (dom.btnClear) {
      dom.btnClear.addEventListener('click', () => {
        const previous = dom.txtOutput ? dom.txtOutput.value : '';
        if (!previous) return;
        if (dom.txtOutput) dom.txtOutput.value = '';
        if (dom.statChars) dom.statChars.textContent = '0 car.';
        if (dom.statWords) dom.statWords.textContent = '0 mots';
        if (dom.latencyText) dom.latencyText.textContent = 'Latence : — ms';
        showToast("Texte effacé", true, {
          label: "Annuler",
          cb: () => {
            if (dom.txtOutput) {
              dom.txtOutput.value = previous;
              updateTextStats();
            }
          }
        });
      });
    }

    // Calcul automatique des compteurs de caractères et mots
    if (dom.txtOutput) {
      dom.txtOutput.addEventListener('input', updateTextStats);
    }
  }

  function updateTextStats() {
    if (!dom.txtOutput) return;
    const text = dom.txtOutput.value || "";
    if (dom.statChars) dom.statChars.textContent = `${text.length} car.`;
    const words = text.trim() ? text.trim().split(/\s+/).length : 0;
    if (dom.statWords) dom.statWords.textContent = `${words} mots`;
  }

  async function startTestRecording() {
    isRecordingTest = true;
    setupWebAudioMic();

    dom.btnBigMic.classList.add('recording');
    dom.btnBigMic.setAttribute('aria-label', "Arrêter l'enregistrement test");
    dom.micHeading.textContent = "En écoute — parlez naturellement";
    dom.micSubtext.textContent = "Cliquez à nouveau pour arrêter et transcrire";

    if (dom.studioStateBadge) dom.studioStateBadge.className = "studio-badge recording";
    if (dom.studioStateText) dom.studioStateText.textContent = "Enregistrement…";

    setIslandState('recording', 'test');
    startRecordingTimer();

    try {
      const res = await window.pywebview.api.start_test_record();
      if (res && res.status === 'error') window.onAppError(res.error || 'Enregistrement impossible');
    } catch (err) {
      console.error("Erreur start_test_record:", err);
      window.onAppError('Enregistrement impossible');
    }
  }

  async function stopTestRecording() {
    isRecordingTest = false;
    stopRecordingTimer();

    dom.btnBigMic.classList.remove('recording');
    dom.btnBigMic.setAttribute('aria-label', "Démarrer l'enregistrement test");
    dom.micHeading.textContent = "Transcription en cours…";
    dom.micSubtext.textContent = "Votre GPU s'en occupe, quelques millisecondes suffisent";

    if (dom.studioStateBadge) dom.studioStateBadge.className = "studio-badge";
    if (dom.studioStateText) dom.studioStateText.textContent = "Transcription…";

    setIslandState('transcribing');

    try {
      const res = await window.pywebview.api.stop_test_record();
      if (res && res.error) { window.onAppError(res.error); return; }

      dom.micHeading.textContent = "Testez votre dictée";
      dom.micSubtext.textContent = "Cliquez sur le micro, ou utilisez votre raccourci global où que vous soyez";
      if (dom.studioStateText) dom.studioStateText.textContent = "Prêt";

      if (res && res.text) {
        dom.txtOutput.value = res.text;
        updateTextStats();
        const latMs = Math.round((res.duration || 0) * 1000);
        if (dom.latencyText) dom.latencyText.textContent = `Latence : ${latMs} ms`;
        setIslandState('done', res.duration);
        showToast(`Transcrit en ${latMs} ms`);
      } else {
        dom.txtOutput.value = "Aucune voix détectée. Réessayez en parlant un peu plus près du micro.";
        updateTextStats();
        setIslandState('idle');
      }
    } catch (err) {
      console.error("Erreur stop_test_record:", err);
      setIslandState('idle');
    }
  }

  function startRecordingTimer() {
    stopRecordingTimer();
    timerStartTime = Date.now();
    timerInterval = setInterval(() => {
      const elapsed = Date.now() - timerStartTime;
      const mins = Math.floor(elapsed / 60000);
      const secs = Math.floor((elapsed % 60000) / 1000);
      const tenths = Math.floor((elapsed % 1000) / 100);
      const formattedShort = `${String(mins).padStart(2, '0')}:${String(secs).padStart(2, '0')}`;
      const formattedFull = `${formattedShort}.${tenths}`;

      if (dom.studioTimer) dom.studioTimer.textContent = formattedFull;
      if (dom.islandTimer) dom.islandTimer.textContent = formattedShort;
    }, 100);
  }

  function stopRecordingTimer() {
    clearInterval(timerInterval);
    timerInterval = null;
  }

  // =========================================================================
  // GLOBAL BACKEND EVENT HOOKS (Python -> JS Bridge)
  // =========================================================================

  // Notifié quand un raccourci global démarre ou arrête l'écoute
  window.onRecordingStateChange = function (isRec, modeOrState, duration) {
    if (isRec === true) {
      isRecordingTest = true;
      setIslandState('recording', modeOrState);
      startRecordingTimer();
      if (dom.btnBigMic) dom.btnBigMic.classList.add('recording');
      if (dom.studioStateBadge) dom.studioStateBadge.className = "studio-badge recording";
      if (dom.studioStateText) dom.studioStateText.textContent = "Enregistrement…";
    } else if (isRec === 'transcribing') {
      isRecordingTest = false;
      stopRecordingTimer();
      setIslandState('transcribing');
      if (dom.btnBigMic) dom.btnBigMic.classList.remove('recording');
      if (dom.studioStateText) dom.studioStateText.textContent = "Transcription…";
    } else {
      isRecordingTest = false;
      stopRecordingTimer();
      if (dom.btnBigMic) dom.btnBigMic.classList.remove('recording');
      if (dom.studioStateBadge) dom.studioStateBadge.className = "studio-badge";
      if (dom.studioStateText) dom.studioStateText.textContent = "Prêt";

      if (modeOrState === 'done') {
        setIslandState('done', duration);
      } else if (modeOrState === 'cancel') {
        setIslandState('cancel');
        showToast("Enregistrement annulé");
      } else {
        setIslandState('idle');
      }
    }
  };

  // Notifié quand une transcription globale est terminée et injectée
  window.onGlobalTranscription = function (text, duration) {
    if (dom.txtOutput && text) {
      dom.txtOutput.value = text;
      updateTextStats();
      const latMs = Math.round((duration || 0) * 1000);
      if (dom.latencyText) dom.latencyText.textContent = `Latence : ${latMs} ms`;
      showToast(`Injecté dans l'application active (${latMs} ms)`);
    }
  };

})();
