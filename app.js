// State Management
const STATE = {
    apiUrl: localStorage.getItem('reup_api_url') || '',
    apiKey: localStorage.getItem('reup_api_key') || '',
    activeTab: 'dashboard',
    monitoredChannels: [],
    destinationChannels: [],
    selectedMonitoredId: null, // channel currently being mapped
    selectedVideo: null,       // video currently selected for manual reup
    manualVideos: [],          // cached scan videos
    activeManualTaskId: null,
    manualPollInterval: null
};

// DOM Elements
const DOM = {
    connectionModal: document.getElementById('connection-modal'),
    inputApiUrl: document.getElementById('input-api-url'),
    inputApiKey: document.getElementById('input-api-key'),
    btnSaveConnection: document.getElementById('btn-save-connection'),
    connectionError: document.getElementById('connection-error'),
    btnDisconnect: document.getElementById('btn-disconnect'),
    backendStatusText: document.getElementById('backend-status-text'),
    statusIndicator: document.querySelector('.status-indicator'),
    
    navItems: document.querySelectorAll('.nav-item'),
    tabPanes: document.querySelectorAll('.tab-pane'),
    pageTitle: document.getElementById('page-title'),
    pageSubtitle: document.getElementById('page-subtitle'),
    
    schedulerBadge: document.getElementById('scheduler-badge'),
    schedulerBadgeText: document.getElementById('scheduler-badge-text'),
    btnToggleScheduler: document.getElementById('btn-toggle-scheduler'),
    
    // Stats
    statMonitored: document.getElementById('stat-monitored'),
    statDestinations: document.getElementById('stat-destinations'),
    statInterval: document.getElementById('stat-interval'),
    statQueue: document.getElementById('stat-queue'),
    logsTerminal: document.getElementById('logs-terminal'),
    btnRefreshLogs: document.getElementById('btn-refresh-logs'),
    
    // Channels & Mappings
    formAddMonitored: document.getElementById('form-add-monitored'),
    addMonPlatform: document.getElementById('add-mon-platform'),
    addMonUrl: document.getElementById('add-mon-url'),
    monitoredList: document.getElementById('monitored-list'),
    mappingChannelTitle: document.getElementById('mapping-channel-title'),
    mappingContainer: document.getElementById('mapping-container'),
    mappingListInputs: document.getElementById('mapping-list-inputs'),
    btnSaveMapping: document.getElementById('btn-save-mapping'),
    
    // Reup Settings
    formReupSettings: document.getElementById('form-reup-settings'),
    reupSpeed: document.getElementById('reup-speed'),
    reupZoom: document.getElementById('reup-zoom'),
    reupIntro: document.getElementById('reup-intro'),
    reupOutro: document.getElementById('reup-outro'),
    reupFlip: document.getElementById('reup-flip'),
    reupPitchEnabled: document.getElementById('reup-pitch-enabled'),
    reupPitchFactor: document.getElementById('reup-pitch-factor'),
    reupColor: document.getElementById('reup-color'),
    reupNoise: document.getElementById('reup-noise'),
    reupVignette: document.getElementById('reup-vignette'),
    reupMetaEnabled: document.getElementById('reup-meta-enabled'),
    reupMusicEnabled: document.getElementById('reup-music-enabled'),
    reupMusicVolume: document.getElementById('reup-music-volume'),
    volumeValDisplay: document.getElementById('volume-val-display'),
    musicUploadZone: document.getElementById('music-upload-zone'),
    musicFileInput: document.getElementById('music-file-input'),
    musicList: document.getElementById('music-list'),
    
    // Manual scan
    manualSourceSelect: document.getElementById('manual-source-select'),
    manualScanType: document.getElementById('manual-scan-type'),
    btnManualScan: document.getElementById('btn-manual-scan'),
    scanResultsContainer: document.getElementById('scan-results-container'),
    resultsCount: document.getElementById('results-count'),
    videosListTbody: document.getElementById('videos-list-tbody'),
    manualProcessInputs: document.getElementById('manual-process-inputs'),
    previewVideoTitle: document.getElementById('preview-video-title'),
    manualDestinationsChecklist: document.getElementById('manual-destinations-checklist'),
    btnStartManual: document.getElementById('btn-start-manual'),
    manualProgressBox: document.getElementById('manual-progress-box'),
    progressStepText: document.getElementById('progress-step-text'),
    progressPctText: document.getElementById('progress-pct-text'),
    progressBarFill: document.getElementById('progress-bar-fill'),
    progressSubText: document.getElementById('progress-sub-text'),
    
    // System Settings & APIs
    formApiAi: document.getElementById('form-api-ai'),
    apiGoogle: document.getElementById('api-google'),
    apiGroq: document.getElementById('api-groq'),
    btnTestGoogle: document.getElementById('btn-test-google'),
    btnTestGroq: document.getElementById('btn-test-groq'),
    formSystemSettings: document.getElementById('form-system-settings'),
    sysPingEnabled: document.getElementById('sys-ping-enabled'),
    sysPingChat: document.getElementById('sys-ping-chat'),
    sysKeepawake: document.getElementById('sys-keepawake'),
    sysScanInterval: document.getElementById('sys-scan-interval'),
    sysBackupToken: document.getElementById('sys-backup-token'),
    sysBackupChat: document.getElementById('sys-backup-chat'),
    
    // Social Credentials
    apiYtTokenText: document.getElementById('api-yt-token-text'),
    btnSaveYtApi: document.getElementById('btn-save-yt-api'),
    btnTestYtApi: document.getElementById('btn-test-yt-api'),
    apiTiktokTokenText: document.getElementById('api-tiktok-token-text'),
    btnSaveTiktokApi: document.getElementById('btn-save-tiktok-api'),
    btnTestTiktokApi: document.getElementById('btn-test-tiktok-api'),
    apiFbTokenText: document.getElementById('api-fb-token-text'),
    btnSaveFbApi: document.getElementById('btn-save-fb-api'),
    btnTestFbApi: document.getElementById('btn-test-fb-api')
};

// Main API request caller
async function apiCall(endpoint, method = 'GET', body = null, isMultipart = false) {
    if (!STATE.apiUrl) {
        showConnectionModal();
        throw new Error('API URL not configured');
    }
    
    const url = `${STATE.apiUrl.replace(/\/$/, '')}/${endpoint.replace(/^\//, '')}`;
    const headers = {
        'X-API-Key': STATE.apiKey
    };
    
    if (!isMultipart && body) {
        headers['Content-Type'] = 'application/json';
    }
    
    const config = {
        method,
        headers,
    };
    
    if (body) {
        config.body = isMultipart ? body : JSON.stringify(body);
    }
    
    const response = await fetch(url, config);
    if (response.status === 401) {
        alert('Lỗi xác thực (401): API Key không chính xác!');
        showConnectionModal();
        throw new Error('Unauthorized');
    }
    
    if (!response.ok) {
        const errorText = await response.text();
        throw new Error(errorText || `API error ${response.status}`);
    }
    
    return response.json();
}

// Display/Hide setup screen
function showConnectionModal() {
    DOM.connectionModal.classList.remove('hidden');
    DOM.inputApiUrl.value = STATE.apiUrl;
    DOM.inputApiKey.value = STATE.apiKey;
    DOM.statusIndicator.className = 'status-indicator offline';
    DOM.backendStatusText.textContent = 'Mất kết nối';
}

function hideConnectionModal() {
    DOM.connectionModal.classList.add('hidden');
}

// Test and save connection info
async function handleConnectionSubmit() {
    const url = DOM.inputApiUrl.value.trim();
    const key = DOM.inputApiKey.value.trim();
    
    if (!url) {
        DOM.connectionError.textContent = 'Vui lòng nhập đường dẫn API URL!';
        DOM.connectionError.classList.remove('hidden');
        return;
    }
    
    DOM.connectionError.textContent = 'Đang kiểm tra kết nối...';
    DOM.connectionError.classList.remove('hidden');
    DOM.btnSaveConnection.disabled = true;
    
    try {
        // Temporarily assign to state for testing connection
        STATE.apiUrl = url;
        STATE.apiKey = key;
        
        // Call status API
        const data = await apiCall('/api/status');
        
        // If success, save to localStorage
        localStorage.setItem('reup_api_url', url);
        localStorage.setItem('reup_api_key', key);
        
        hideConnectionModal();
        DOM.btnSaveConnection.disabled = false;
        
        // Re-initialize app
        initApp();
    } catch (err) {
        DOM.connectionError.textContent = `Kết nối thất bại: ${err.message}. Hãy kiểm tra lại URL và X-API-Key.`;
        DOM.btnSaveConnection.disabled = false;
        STATE.apiUrl = '';
        STATE.apiKey = '';
    }
}

// App routing and tabs
function setupTabs() {
    DOM.navItems.forEach(item => {
        item.addEventListener('click', (e) => {
            e.preventDefault();
            const tabName = item.getAttribute('data-tab');
            switchTab(tabName);
        });
    });
}

function switchTab(tabName) {
    STATE.activeTab = tabName;
    
    // Update active navbar item
    DOM.navItems.forEach(item => {
        if (item.getAttribute('data-tab') === tabName) {
            item.classList.add('active');
        } else {
            item.classList.remove('active');
        }
    });
    
    // Update active tab contents
    DOM.tabPanes.forEach(pane => {
        if (pane.getAttribute('id') === `tab-${tabName}`) {
            pane.classList.add('active');
        } else {
            pane.classList.remove('active');
        }
    });
    
    // Set page headers
    const titles = {
        dashboard: { title: 'Dashboard', subtitle: 'Tổng quan hệ thống tự động hóa reup video.' },
        channels: { title: 'Kênh & Ánh xạ', subtitle: 'Quản lý danh sách kênh nguồn và cấu hình đăng tải kênh đích.' },
        reup: { title: 'Cấu hình Reup', subtitle: 'Thiết lập tham số chỉnh sửa video, nhạc nền và cơ chế lách bản quyền.' },
        manual: { title: 'Quét & Xử lý thủ công', subtitle: 'Quét danh sách video từ kênh nguồn và đăng tải lên kênh đích tức thời.' },
        settings: { title: 'Cài đặt hệ thống', subtitle: 'Cấu hình Google AI Studio, Groq API, Token mạng xã hội và Active Ping.' }
    };
    
    const info = titles[tabName] || { title: 'Control Panel', subtitle: '' };
    DOM.pageTitle.textContent = info.title;
    DOM.pageSubtitle.textContent = info.subtitle;
    
    // Fetch tab specific data
    loadTabData(tabName);
}

// Fetch tab specific data
function loadTabData(tabName) {
    if (tabName === 'dashboard') {
        loadDashboardStats();
        loadLogs();
    } else if (tabName === 'channels') {
        loadChannelsAndMappings();
    } else if (tabName === 'reup') {
        loadReupSettings();
        loadMusicLibrary();
    } else if (tabName === 'manual') {
        loadManualChannelsDropdown();
    } else if (tabName === 'settings') {
        loadSystemSettings();
        loadApiStatusList();
    }
}

// ----------------- TAB: DASHBOARD -----------------

async function loadDashboardStats() {
    try {
        const stats = await apiCall('/api/status');
        
        DOM.statMonitored.textContent = stats.monitored_count;
        DOM.statDestinations.textContent = stats.destination_count;
        DOM.statInterval.textContent = stats.scan_interval;
        DOM.statQueue.textContent = stats.queue_count;
        
        // Update Scheduler status badge
        if (stats.auto_mode_enabled) {
            DOM.schedulerBadge.className = 'badge active';
            DOM.schedulerBadgeText.textContent = 'Scheduler Đang chạy';
        } else {
            DOM.schedulerBadge.className = 'badge paused';
            DOM.schedulerBadgeText.textContent = 'Scheduler Đang tạm dừng';
        }
        
        DOM.statusIndicator.className = 'status-indicator online';
        DOM.backendStatusText.textContent = 'Đã kết nối';
    } catch (err) {
        console.error('Failed to load stats:', err);
    }
}

async function loadLogs() {
    try {
        const logs = await apiCall('/api/logs?limit=40');
        DOM.logsTerminal.innerHTML = '';
        
        if (logs.length === 0) {
            DOM.logsTerminal.innerHTML = '<div class="log-line text-muted">Không có nhật ký hoạt động nào.</div>';
            return;
        }
        
        logs.forEach(log => {
            const row = document.createElement('div');
            row.className = `log-line ${log.level.toLowerCase()}`;
            
            const tsSpan = document.createElement('span');
            tsSpan.className = 'log-line timestamp';
            tsSpan.textContent = `[${log.timestamp}] `;
            
            const lvlSpan = document.createElement('span');
            lvlSpan.textContent = `[${log.level}] `;
            
            const msgSpan = document.createElement('span');
            msgSpan.textContent = log.message;
            
            row.appendChild(tsSpan);
            row.appendChild(lvlSpan);
            row.appendChild(msgSpan);
            
            DOM.logsTerminal.appendChild(row);
        });
        
        // Auto scroll terminal to bottom
        DOM.logsTerminal.scrollTop = DOM.logsTerminal.scrollHeight;
    } catch (err) {
        console.error('Failed to load logs:', err);
    }
}

async function handleToggleScheduler() {
    try {
        const data = await apiCall('/api/scheduler/toggle', 'POST');
        if (data.status === 'success') {
            loadDashboardStats();
            setTimeout(loadLogs, 1000);
        }
    } catch (err) {
        alert('Lỗi khi thay đổi trạng thái scheduler: ' + err.message);
    }
}

// ----------------- TAB: CHANNELS & MAPPINGS -----------------

async function loadChannelsAndMappings() {
    try {
        // Load Monitored
        const monitored = await apiCall('/api/monitored-channels');
        STATE.monitoredChannels = monitored;
        
        // Load Destinations
        const destinations = await apiCall('/api/destination-channels');
        STATE.destinationChannels = destinations;
        
        renderMonitoredChannelsList();
    } catch (err) {
        console.error('Error loading channels:', err);
    }
}

function renderMonitoredChannelsList() {
    DOM.monitoredList.innerHTML = '';
    
    if (STATE.monitoredChannels.length === 0) {
        DOM.monitoredList.innerHTML = '<p class="text-muted text-sm p-4">Chưa có kênh giám sát nào. Thêm bằng URL bên trên.</p>';
        return;
    }
    
    STATE.monitoredChannels.forEach(channel => {
        const row = document.createElement('div');
        row.className = `channel-row ${STATE.selectedMonitoredId === channel.id ? 'active' : ''}`;
        row.setAttribute('data-id', channel.id);
        
        const platformClass = `${channel.platform.toLowerCase()}-bg`;
        let platformIcon = 'link-2';
        if (channel.platform.toLowerCase() === 'youtube') platformIcon = 'youtube';
        if (channel.platform.toLowerCase() === 'tiktok') platformIcon = 'music';
        if (channel.platform.toLowerCase() === 'facebook') platformIcon = 'facebook';
        
        row.innerHTML = `
            <div class="channel-info">
                <div class="channel-platform-icon ${platformClass}">
                    <i data-lucide="${platformIcon}"></i>
                </div>
                <div style="overflow: hidden;">
                    <div class="channel-name">${channel.channel_name}</div>
                    <div class="channel-url">${channel.url}</div>
                </div>
            </div>
            <button class="btn-icon btn-delete-monitored" data-id="${channel.id}">
                <i data-lucide="trash-2"></i>
            </button>
        `;
        
        // Click to configure mapping
        row.addEventListener('click', (e) => {
            if (e.target.closest('.btn-delete-monitored')) return;
            selectMonitoredChannelForMapping(channel.id);
        });
        
        DOM.monitoredList.appendChild(row);
    });
    
    lucide.createIcons();
    
    // Bind deletes
    document.querySelectorAll('.btn-delete-monitored').forEach(btn => {
        btn.addEventListener('click', async (e) => {
            e.stopPropagation();
            const id = btn.getAttribute('data-id');
            if (confirm('Bạn có chắc chắn muốn xóa kênh giám sát này?')) {
                try {
                    await apiCall(`/api/monitored-channels/${id}`, 'DELETE');
                    if (STATE.selectedMonitoredId == id) {
                        STATE.selectedMonitoredId = null;
                        resetMappingPane();
                    }
                    loadChannelsAndMappings();
                } catch (err) {
                    alert('Lỗi khi xóa kênh: ' + err.message);
                }
            }
        });
    });
}

function resetMappingPane() {
    DOM.mappingChannelTitle.textContent = 'Chọn kênh giám sát để cấu hình';
    DOM.mappingContainer.classList.add('disabled');
    DOM.mappingListInputs.classList.add('hidden');
    DOM.btnSaveMapping.classList.add('hidden');
    DOM.mappingContainer.querySelector('.placeholder-text').classList.remove('hidden');
}

async function selectMonitoredChannelForMapping(channelId) {
    STATE.selectedMonitoredId = channelId;
    
    // Highlight item
    document.querySelectorAll('.channel-row').forEach(row => {
        if (row.getAttribute('data-id') == channelId) {
            row.classList.add('active');
        } else {
            row.classList.remove('active');
        }
    });
    
    const channel = STATE.monitoredChannels.find(c => c.id === channelId);
    if (!channel) return;
    
    DOM.mappingChannelTitle.textContent = `Ánh xạ kênh nguồn: ${channel.channel_name}`;
    DOM.mappingContainer.classList.remove('disabled');
    DOM.mappingContainer.querySelector('.placeholder-text').classList.add('hidden');
    DOM.mappingListInputs.classList.remove('hidden');
    DOM.btnSaveMapping.classList.remove('hidden');
    
    try {
        // Fetch current mappings
        const mappedDestIds = await apiCall(`/api/mappings/${channelId}`);
        
        // Render checkboxes
        DOM.mappingListInputs.innerHTML = '';
        
        if (STATE.destinationChannels.length === 0) {
            DOM.mappingListInputs.innerHTML = '<p class="text-muted text-sm p-4">Chưa phát hiện kênh đích nào. Vui lòng cấu hình API Tokens trong tab Cài đặt để đồng bộ kênh đích tự động.</p>';
            DOM.btnSaveMapping.classList.add('hidden');
            return;
        }
        
        STATE.destinationChannels.forEach(dest => {
            const isChecked = mappedDestIds.includes(dest.id);
            const label = document.createElement('label');
            label.className = 'checkbox-item';
            label.innerHTML = `
                <input type="checkbox" value="${dest.id}" ${isChecked ? 'checked' : ''}>
                <span class="checkbox-item-label">${dest.channel_name} (${dest.channel_id})</span>
                <span class="checkbox-item-platform">${dest.platform}</span>
            `;
            DOM.mappingListInputs.appendChild(label);
        });
    } catch (err) {
        console.error('Error fetching channel mapping:', err);
    }
}

async function handleAddMonitoredChannel(e) {
    e.preventDefault();
    const platform = DOM.addMonPlatform.value;
    const url = DOM.addMonUrl.value.trim();
    
    if (!url) return;
    
    const submitBtn = DOM.formAddMonitored.querySelector('button[type="submit"]');
    submitBtn.disabled = true;
    submitBtn.innerHTML = 'Đang thêm...';
    
    try {
        const res = await apiCall('/api/monitored-channels', 'POST', { platform, url });
        if (res.status === 'success') {
            DOM.addMonUrl.value = '';
            loadChannelsAndMappings();
        } else {
            alert('Lỗi: ' + res.error);
        }
    } catch (err) {
        alert('Lỗi kết nối khi thêm kênh: ' + err.message);
    } finally {
        submitBtn.disabled = false;
        submitBtn.innerHTML = '<i data-lucide="plus"></i> Thêm';
        lucide.createIcons();
    }
}

async function handleSaveMapping() {
    if (!STATE.selectedMonitoredId) return;
    
    const checkedInputs = DOM.mappingListInputs.querySelectorAll('input[type="checkbox"]:checked');
    const destinationIds = Array.from(checkedInputs).map(inp => parseInt(inp.value));
    
    DOM.btnSaveMapping.disabled = true;
    DOM.btnSaveMapping.textContent = 'Đang lưu...';
    
    try {
        const res = await apiCall(`/api/mappings/${STATE.selectedMonitoredId}`, 'POST', { destination_ids: destinationIds });
        if (res.status === 'success') {
            alert('Đã lưu cấu hình ánh xạ thành công!');
        }
    } catch (err) {
        alert('Lỗi khi lưu ánh xạ: ' + err.message);
    } finally {
        DOM.btnSaveMapping.disabled = false;
        DOM.btnSaveMapping.innerHTML = '<i data-lucide="save"></i> Lưu cấu hình ánh xạ';
        lucide.createIcons();
    }
}

// ----------------- TAB: REUP CONFIGS & MUSIC -----------------

async function loadReupSettings() {
    try {
        const settings = await apiCall('/api/reup-settings');
        
        DOM.reupSpeed.value = settings.speed || '1.0';
        DOM.reupZoom.value = settings.zoom || '1.0';
        DOM.reupIntro.value = settings.intro_cut || '0.0';
        DOM.reupOutro.value = settings.outro_cut || '0.0';
        DOM.reupFlip.checked = settings.flip_horizontal === 'true';
        DOM.reupPitchEnabled.checked = settings.copyright_pitch_enabled === 'true';
        DOM.reupPitchFactor.value = settings.copyright_pitch_factor || '1.02';
        DOM.reupColor.checked = settings.copyright_color_enabled === 'true';
        DOM.reupNoise.checked = settings.copyright_noise_enabled === 'true';
        DOM.reupVignette.checked = settings.copyright_vignette_enabled === 'true';
        DOM.reupMetaEnabled.checked = settings.metadata_rewrite_enabled === 'true';
        
        DOM.reupMusicEnabled.checked = settings.bg_music_enabled === 'true';
        DOM.reupMusicVolume.value = settings.music_volume || '0.5';
        DOM.volumeValDisplay.textContent = Math.round((settings.music_volume || 0.5) * 100) + '%';
        
        togglePitchFactorVisibility();
    } catch (err) {
        console.error('Failed to load reup settings:', err);
    }
}

function togglePitchFactorVisibility() {
    const group = document.getElementById('group-pitch-factor');
    if (DOM.reupPitchEnabled.checked) {
        group.classList.remove('hidden');
    } else {
        group.classList.add('hidden');
    }
}

async function handleReupSettingsSubmit(e) {
    e.preventDefault();
    const settings = {
        speed: DOM.reupSpeed.value,
        zoom: DOM.reupZoom.value,
        intro_cut: DOM.reupIntro.value,
        outro_cut: DOM.reupOutro.value,
        flip_horizontal: DOM.reupFlip.checked ? 'true' : 'false',
        copyright_pitch_enabled: DOM.reupPitchEnabled.checked ? 'true' : 'false',
        copyright_pitch_factor: DOM.reupPitchFactor.value,
        copyright_color_enabled: DOM.reupColor.checked ? 'true' : 'false',
        copyright_noise_enabled: DOM.reupNoise.checked ? 'true' : 'false',
        copyright_vignette_enabled: DOM.reupVignette.checked ? 'true' : 'false',
        metadata_rewrite_enabled: DOM.reupMetaEnabled.checked ? 'true' : 'false',
        bg_music_enabled: DOM.reupMusicEnabled.checked ? 'true' : 'false',
        music_volume: DOM.reupMusicVolume.value
    };
    
    const submitBtn = DOM.formReupSettings.querySelector('button[type="submit"]');
    submitBtn.disabled = true;
    submitBtn.textContent = 'Đang lưu cài đặt...';
    
    try {
        const res = await apiCall('/api/reup-settings', 'POST', settings);
        if (res.status === 'success') {
            alert('Cập nhật cấu hình reup thành công!');
        }
    } catch (err) {
        alert('Lỗi kết nối khi cập nhật cấu hình: ' + err.message);
    } finally {
        submitBtn.disabled = false;
        submitBtn.innerHTML = '<i data-lucide="check-circle2"></i> Lưu cài đặt Video';
        lucide.createIcons();
    }
}

async function loadMusicLibrary() {
    try {
        const musicFiles = await apiCall('/api/music');
        DOM.musicList.innerHTML = '';
        
        if (musicFiles.length === 0) {
            DOM.musicList.innerHTML = '<p class="text-muted text-sm p-2">Thư viện nhạc nền trống.</p>';
            return;
        }
        
        musicFiles.forEach(file => {
            const sizeMb = (file.file_size / (1024 * 1024)).toFixed(2);
            const row = document.createElement('div');
            row.className = 'music-row';
            row.innerHTML = `
                <div class="music-name">${file.filename}</div>
                <div class="music-size">${sizeMb} MB</div>
                <button class="btn-icon btn-delete-music" data-id="${file.id}">
                    <i data-lucide="trash-2"></i>
                </button>
            `;
            DOM.musicList.appendChild(row);
        });
        
        lucide.createIcons();
        
        // Bind deletes
        document.querySelectorAll('.btn-delete-music').forEach(btn => {
            btn.addEventListener('click', async () => {
                const id = btn.getAttribute('data-id');
                if (confirm('Xóa file nhạc nền này khỏi thư viện?')) {
                    try {
                        await apiCall(`/api/music/${id}`, 'DELETE');
                        loadMusicLibrary();
                    } catch (err) {
                        alert('Xóa nhạc thất bại: ' + err.message);
                    }
                }
            });
        });
    } catch (err) {
        console.error('Failed to load music files:', err);
    }
}

function setupMusicUpload() {
    DOM.musicUploadZone.addEventListener('click', () => {
        DOM.musicFileInput.click();
    });
    
    DOM.musicFileInput.addEventListener('change', (e) => {
        const file = e.target.files[0];
        if (file) {
            uploadMusicFile(file);
        }
    });
}

async function uploadMusicFile(file) {
    if (file.type !== 'audio/mpeg' && !file.name.endsWith('.mp3')) {
        alert('Vui lòng chỉ tải lên file định dạng .mp3');
        return;
    }
    
    const formData = new FormData();
    formData.append('file', file);
    
    DOM.musicUploadZone.querySelector('p').textContent = `Đang tải lên: ${file.name}...`;
    DOM.musicUploadZone.style.opacity = '0.5';
    
    try {
        const res = await apiCall('/api/music', 'POST', formData, true);
        if (res.status === 'success') {
            loadMusicLibrary();
        }
    } catch (err) {
        alert('Tải lên nhạc nền thất bại: ' + err.message);
    } finally {
        DOM.musicUploadZone.querySelector('p').textContent = 'Kéo thả file nhạc hoặc bấm vào đây để upload (.mp3)';
        DOM.musicUploadZone.style.opacity = '1';
        DOM.musicFileInput.value = '';
    }
}

// ----------------- TAB: MANUAL MODE -----------------

async function loadManualChannelsDropdown() {
    try {
        const monitored = await apiCall('/api/monitored-channels');
        DOM.manualSourceSelect.innerHTML = '<option value="">-- Chọn kênh nguồn --</option>';
        
        monitored.forEach(ch => {
            const opt = document.createElement('option');
            opt.value = ch.id;
            opt.textContent = `${ch.channel_name} (${ch.platform})`;
            DOM.manualSourceSelect.appendChild(opt);
        });
        
        // Dest options Checklist
        const destinations = await apiCall('/api/destination-channels');
        DOM.manualDestinationsChecklist.innerHTML = '';
        
        if (destinations.length === 0) {
            DOM.manualDestinationsChecklist.innerHTML = '<p class="text-muted text-sm p-4">Không có kênh đích nào khả dụng.</p>';
            return;
        }
        
        destinations.forEach(dest => {
            const label = document.createElement('label');
            label.className = 'checkbox-item';
            label.innerHTML = `
                <input type="checkbox" name="manual-dest" value="${dest.id}">
                <span class="checkbox-item-label">${dest.channel_name}</span>
                <span class="checkbox-item-platform">${dest.platform}</span>
            `;
            DOM.manualDestinationsChecklist.appendChild(label);
        });
    } catch (err) {
        console.error('Error loading manual mode options:', err);
    }
}

async function handleManualScan() {
    const channelId = DOM.manualSourceSelect.value;
    const scanType = DOM.manualScanType.value;
    
    if (!channelId) {
        alert('Vui lòng chọn kênh nguồn!');
        return;
    }
    
    DOM.btnManualScan.disabled = true;
    DOM.btnManualScan.innerHTML = 'Đang quét...';
    DOM.scanResultsContainer.classList.add('hidden');
    DOM.manualProcessInputs.classList.add('disabled');
    
    try {
        const data = await apiCall('/api/manual/scan', 'POST', { channel_id: parseInt(channelId), scan_type: scanType });
        if (data.status === 'success') {
            STATE.manualVideos = data.videos;
            renderManualScanResults();
        }
    } catch (err) {
        alert('Lỗi quét kênh: ' + err.message);
    } finally {
        DOM.btnManualScan.disabled = false;
        DOM.btnManualScan.innerHTML = '<i data-lucide="search"></i> Quét Video';
        lucide.createIcons();
    }
}

function renderManualScanResults() {
    DOM.videosListTbody.innerHTML = '';
    
    if (STATE.manualVideos.length === 0) {
        DOM.resultsCount.textContent = '0 video';
        DOM.videosListTbody.innerHTML = '<tr><td colspan="4" class="text-center text-muted">Không tìm thấy video nào. Hãy đổi kiểu quét.</td></tr>';
        DOM.scanResultsContainer.classList.remove('hidden');
        return;
    }
    
    DOM.resultsCount.textContent = `${STATE.manualVideos.length} video`;
    
    STATE.manualVideos.forEach(vid => {
        const row = document.createElement('tr');
        row.innerHTML = `
            <td>
                <input type="radio" name="select-video" value="${vid.id}">
            </td>
            <td>
                <div class="video-scan-title">${vid.title}</div>
                <div class="video-scan-url">${vid.url}</div>
            </td>
            <td><code>${vid.id}</code></td>
            <td>
                <a href="${vid.url}" target="_blank" class="btn btn-secondary btn-sm"><i data-lucide="external-link"></i> Xem</a>
            </td>
        `;
        
        // Listen to radio select
        row.querySelector('input[type="radio"]').addEventListener('change', () => {
            selectVideoForProcessing(vid);
        });
        
        DOM.videosListTbody.appendChild(row);
    });
    
    lucide.createIcons();
    DOM.scanResultsContainer.classList.remove('hidden');
}

function selectVideoForProcessing(video) {
    STATE.selectedVideo = video;
    DOM.previewVideoTitle.textContent = video.title;
    DOM.manualProcessInputs.classList.remove('disabled');
}

async function handleStartManualProcessing() {
    if (!STATE.selectedVideo) return;
    
    const checkboxes = DOM.manualDestinationsChecklist.querySelectorAll('input[type="checkbox"]:checked');
    const destinationIds = Array.from(checkboxes).map(chk => parseInt(chk.value));
    
    if (destinationIds.length === 0) {
        alert('Vui lòng chọn ít nhất một kênh đích!');
        return;
    }
    
    DOM.btnStartManual.disabled = true;
    DOM.btnStartManual.textContent = 'Đang khởi chạy...';
    
    try {
        const data = await apiCall('/api/manual/process', 'POST', {
            video_url: STATE.selectedVideo.url,
            video_title: STATE.selectedVideo.title,
            video_id: STATE.selectedVideo.id,
            destination_ids: destinationIds
        });
        
        if (data.status === 'success') {
            STATE.activeManualTaskId = data.task_id;
            DOM.manualProgressBox.classList.remove('hidden');
            DOM.progressBarFill.style.width = '0%';
            DOM.progressPctText.textContent = '0%';
            DOM.progressStepText.textContent = 'Khởi tạo...';
            DOM.progressSubText.textContent = 'Pipeline xử lý video reup đã được khởi chạy.';
            
            // Start Polling progress
            startPollingManualProgress();
        }
    } catch (err) {
        alert('Lỗi kích hoạt tiến trình reup: ' + err.message);
        DOM.btnStartManual.disabled = false;
        DOM.btnStartManual.innerHTML = '<i data-lucide="play"></i> Bắt đầu Reup ngay';
        lucide.createIcons();
    }
}

function startPollingManualProgress() {
    if (STATE.manualPollInterval) clearInterval(STATE.manualPollInterval);
    
    STATE.manualPollInterval = setInterval(async () => {
        if (!STATE.activeManualTaskId) {
            clearInterval(STATE.manualPollInterval);
            return;
        }
        
        try {
            const status = await apiCall(`/api/manual/process/${STATE.activeManualTaskId}`);
            DOM.progressBarFill.style.width = `${status.percent}%`;
            DOM.progressPctText.textContent = `${status.percent}%`;
            DOM.progressStepText.textContent = status.step;
            
            if (status.status === 'completed') {
                clearInterval(STATE.manualPollInterval);
                DOM.progressSubText.textContent = '🟢 Reup thành công tất cả các kênh đích!';
                DOM.btnStartManual.disabled = false;
                DOM.btnStartManual.innerHTML = '<i data-lucide="play"></i> Bắt đầu Reup ngay';
                lucide.createIcons();
            } else if (status.status === 'failed') {
                clearInterval(STATE.manualPollInterval);
                DOM.progressSubText.textContent = `❌ Thất bại: ${status.error || 'Lỗi không xác định khi render/upload'}`;
                DOM.btnStartManual.disabled = false;
                DOM.btnStartManual.innerHTML = '<i data-lucide="play"></i> Bắt đầu Reup ngay';
                lucide.createIcons();
            }
        } catch (err) {
            console.error('Progress poll failed:', err);
        }
    }, 2000);
}

// ----------------- TAB: SETTINGS & APIs -----------------

async function loadSystemSettings() {
    try {
        const settings = await apiCall('/api/system-settings');
        DOM.sysPingEnabled.checked = settings.ping_alive_enabled;
        DOM.sysPingChat.value = settings.ping_chat_id;
        DOM.sysKeepawake.value = settings.keep_awake_url;
        DOM.sysScanInterval.value = settings.scan_interval || '01:00:00';
        DOM.sysBackupToken.value = settings.backup_bot_token;
        DOM.sysBackupChat.value = settings.backup_chat_id;
    } catch (err) {
        console.error('Failed to load system configs:', err);
    }
}

async function handleSystemSettingsSubmit(e) {
    e.preventDefault();
    const settings = {
        ping_alive_enabled: DOM.sysPingEnabled.checked,
        ping_chat_id: DOM.sysPingChat.value.trim(),
        keep_awake_url: DOM.sysKeepawake.value.trim(),
        scan_interval: DOM.sysScanInterval.value.trim(),
        backup_bot_token: DOM.sysBackupToken.value.trim(),
        backup_chat_id: DOM.sysBackupChat.value.trim()
    };
    
    const btn = DOM.formSystemSettings.querySelector('button[type="submit"]');
    btn.disabled = true;
    btn.textContent = 'Đang lưu cấu hình...';
    
    try {
        const res = await apiCall('/api/system-settings', 'POST', settings);
        if (res.status === 'success') {
            alert('Lưu cài đặt hệ thống thành công!');
        }
    } catch (err) {
        alert('Lưu thất bại: ' + err.message);
    } finally {
        btn.disabled = false;
        btn.innerHTML = '<i data-lucide="save"></i> Lưu Cấu hình Hệ thống';
        lucide.createIcons();
    }
}

async function loadApiStatusList() {
    try {
        const apis = await apiCall('/api/apis');
        apis.forEach(api => {
            const inputField = document.getElementById(`api-${api.platform}`);
            if (inputField) {
                // If connected, show a masked placeholder
                inputField.value = api.connected ? '••••••••••••••••••••••••••••••••' : '';
            }
        });
    } catch (err) {
        console.error('Error loading APIs:', err);
    }
}

async function handleApiAiSubmit(e) {
    e.preventDefault();
    const googleVal = DOM.apiGoogle.value.trim();
    const groqVal = DOM.apiGroq.value.trim();
    
    let successCount = 0;
    
    try {
        if (googleVal && googleVal !== '••••••••••••••••••••••••••••••••') {
            await apiCall('/api/apis', 'POST', { platform: 'google_ai_studio', token: googleVal });
            successCount++;
        }
        if (groqVal && groqVal !== '••••••••••••••••••••••••••••••••') {
            await apiCall('/api/apis', 'POST', { platform: 'groq', token: groqVal });
            successCount++;
        }
        
        if (successCount > 0) {
            alert('Cập nhật API Key thành công!');
            loadApiStatusList();
        }
    } catch (err) {
        alert('Lỗi cập nhật token: ' + err.message);
    }
}

async function testApiAi(platform, btn) {
    btn.disabled = true;
    btn.textContent = 'Đang test...';
    
    try {
        const data = await apiCall(`/api/apis/${platform}/test`, 'POST');
        if (data.status === 'success') {
            const failItem = data.results.find(r => !r.success);
            if (failItem) {
                alert(`Test thất bại: ${failItem.error}`);
            } else {
                alert(`Kết nối ${platform} thành công và phản hồi tốt!`);
            }
        } else {
            alert(`Lỗi: ${data.error}`);
        }
    } catch (err) {
        alert('Test kết nối thất bại: ' + err.message);
    } finally {
        btn.disabled = false;
        btn.textContent = platform === 'google_ai_studio' ? 'Test Google AI' : 'Test Groq';
    }
}

// Bind Social credentials update/test
function setupSocialApiBindings() {
    const bindSocial = (platform, textEl, saveBtn, testBtn) => {
        saveBtn.addEventListener('click', async () => {
            const token = textEl.value.trim();
            if (!token) {
                alert('Vui lòng điền nội dung token/credentials!');
                return;
            }
            saveBtn.disabled = true;
            try {
                await apiCall('/api/apis', 'POST', { platform, token });
                alert(`Lưu và đồng bộ cấu hình ${platform} thành công!`);
                textEl.value = '••••••••••••••••••••••••••••••••';
            } catch (err) {
                alert('Đồng bộ thất bại: ' + err.message);
            } finally {
                saveBtn.disabled = false;
            }
        });
        
        testBtn.addEventListener('click', async () => {
            testBtn.disabled = true;
            testBtn.textContent = 'Đang test...';
            try {
                const data = await apiCall(`/api/apis/${platform}/test`, 'POST');
                if (data.status === 'success') {
                    const fail = data.results.find(r => !r.success);
                    if (fail) {
                        alert(`Kết nối lỗi: ${fail.error}`);
                    } else {
                        const channelNames = data.results.map(r => r.channel_name).join(', ');
                        alert(`Kết nối thành công! Danh sách kênh phát hiện: [${channelNames}]`);
                    }
                } else {
                    alert(`Lỗi: ${data.error}`);
                }
            } catch (err) {
                alert('Kiểm tra lỗi: ' + err.message);
            } finally {
                testBtn.disabled = false;
                testBtn.textContent = 'Kiểm tra kết nối';
            }
        });
    };
    
    bindSocial('youtube', DOM.apiYtTokenText, DOM.btnSaveYtApi, DOM.btnTestYtApi);
    bindSocial('tiktok', DOM.apiTiktokTokenText, DOM.btnSaveTiktokApi, DOM.btnTestTiktokApi);
    bindSocial('facebook', DOM.apiFbTokenText, DOM.btnSaveFbApi, DOM.btnTestFbApi);
}

// ----------------- INIT & BINDINGS -----------------

function initApp() {
    if (!STATE.apiUrl) {
        showConnectionModal();
        return;
    }
    
    hideConnectionModal();
    
    // Load initial tab data
    switchTab(STATE.activeTab);
    
    // Interval update Dashboard stats
    setInterval(() => {
        if (STATE.activeTab === 'dashboard') {
            loadDashboardStats();
            loadLogs();
        }
    }, 15000);
}

// Global Event Listeners Setup
function setupEventListeners() {
    // Connection Save
    DOM.btnSaveConnection.addEventListener('click', handleConnectionSubmit);
    DOM.btnDisconnect.addEventListener('click', () => {
        if (confirm('Ngắt kết nối với Backend hiện tại?')) {
            localStorage.removeItem('reup_api_url');
            localStorage.removeItem('reup_api_key');
            STATE.apiUrl = '';
            STATE.apiKey = '';
            showConnectionModal();
        }
    });
    
    // Toggle Scheduler
    DOM.btnToggleScheduler.addEventListener('click', handleToggleScheduler);
    DOM.btnRefreshLogs.addEventListener('click', loadLogs);
    
    // Tab setup
    setupTabs();
    
    // Channels
    DOM.formAddMonitored.addEventListener('submit', handleAddMonitoredChannel);
    DOM.btnSaveMapping.addEventListener('click', handleSaveMapping);
    
    // Reup
    DOM.formReupSettings.addEventListener('submit', handleReupSettingsSubmit);
    DOM.reupPitchEnabled.addEventListener('change', togglePitchFactorVisibility);
    DOM.reupMusicVolume.addEventListener('input', (e) => {
        DOM.volumeValDisplay.textContent = Math.round(e.target.value * 100) + '%';
    });
    setupMusicUpload();
    
    // Manualscan
    DOM.btnManualScan.addEventListener('click', handleManualScan);
    DOM.btnStartManual.addEventListener('click', handleStartManualProcessing);
    
    // APIs and Systems
    DOM.formApiAi.addEventListener('submit', handleApiAiSubmit);
    DOM.btnTestGoogle.addEventListener('click', () => testApiAi('google_ai_studio', DOM.btnTestGoogle));
    DOM.btnTestGroq.addEventListener('click', () => testApiAi('groq', DOM.btnTestGroq));
    DOM.formSystemSettings.addEventListener('submit', handleSystemSettingsSubmit);
    setupSocialApiBindings();
}

// Initialize on page load
window.addEventListener('DOMContentLoaded', () => {
    setupEventListeners();
    initApp();
});
