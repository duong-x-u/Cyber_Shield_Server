// static/admin.js

document.addEventListener('DOMContentLoaded', () => {
    // --- Elements for Config Editor ---
    const configEditor = document.getElementById('config-editor');
    const saveConfigBtn = document.getElementById('save-config-btn');
    const configStatus = document.getElementById('config-status-message');

    // --- Elements for File Editor ---
    const fileBrowser = document.getElementById('file-browser');
    const fileEditor = document.getElementById('file-editor');
    const saveFileBtn = document.getElementById('save-file-btn');
    const fileStatus = document.getElementById('file-status-message');
    const currentFilepathEl = document.getElementById('current-filepath');

    // --- Elements for System Metrics ---
    const cpuValue = document.getElementById('cpu-value');
    const cpuProgress = document.getElementById('cpu-progress');
    const ramValue = document.getElementById('ram-value');
    const ramProgress = document.getElementById('ram-progress');
    const diskValue = document.getElementById('disk-value');
    const diskProgress = document.getElementById('disk-progress');

    // --- Helper to show status messages ---
    function showStatus(element, message, isError = false) {
        element.textContent = message;
        element.className = isError ? 'error' : 'success';
    }

    // --- SYSTEM METRICS LOGIC ---
    async function updateSystemMetrics() {
        try {
            const response = await fetch('/admin/api/system-metrics');
            if (!response.ok) {
                // Don't show a big error, just fail silently
                console.error('Failed to fetch system metrics');
                return;
            }
            const metrics = await response.json();
            
            cpuValue.textContent = metrics.cpu.toFixed(1);
            cpuProgress.style.width = `${metrics.cpu}%`;

            ramValue.textContent = metrics.ram.toFixed(1);
            ramProgress.style.width = `${metrics.ram}%`;

            diskValue.textContent = metrics.disk.toFixed(1);
            diskProgress.style.width = `${metrics.disk}%`;

        } catch (error) {
            console.error('Error updating system metrics:', error);
        }
    }

    // --- CONFIG EDITOR LOGIC ---
    async function loadConfig() {
        try {
            const response = await fetch('/admin/api/config');
            if (!response.ok) throw new Error((await response.json()).error || 'Network error');
            const config = await response.json();
            configEditor.value = JSON.stringify(config, null, 2);
        } catch (error) {
            showStatus(configStatus, `Lỗi khi tải config: ${error.message}`, true);
        }
    }


    saveConfigBtn.addEventListener('click', async () => {
        let newConfig;
        try {
            newConfig = JSON.parse(configEditor.value);
        } catch (error) {
            showStatus(configStatus, 'Lỗi: Nội dung không phải là JSON hợp lệ.', true);
            return;
        }

        try {
            const response = await fetch('/admin/api/config', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(newConfig),
            });
            const result = await response.json();
            if (!response.ok) throw new Error(result.error);
            showStatus(configStatus, result.message || 'Cập nhật thành công!');
            await loadConfig();
        } catch (error) {
            showStatus(configStatus, `Lỗi khi lưu config: ${error.message}`, true);
        }
    });

    // --- FILE EDITOR LOGIC ---
    
    let currentOpenFilePath = '';

    async function loadFileList(path = '.') {
        try {
            const response = await fetch(`/admin/api/files?path=${encodeURIComponent(path)}`);
            if (!response.ok) throw new Error((await response.json()).error || 'Network error');
            const items = await response.json();
            renderFileBrowser(items, path);
        } catch (error) {
            showStatus(fileStatus, `Lỗi khi tải danh sách file: ${error.message}`, true);
        }
    }
    
    function renderFileBrowser(items, currentPath) {
        fileBrowser.innerHTML = '';
        const ul = document.createElement('ul');

        // Add "go up" link if not in root
        if (currentPath !== '.') {
            const parentPath = currentPath.substring(0, currentPath.lastIndexOf('/')) || '.';
            const li = document.createElement('li');
            li.innerHTML = `<span class="icon">⬆️</span> ..`;
            li.dataset.path = parentPath;
            li.dataset.type = 'directory';
            ul.appendChild(li);
        }

        items.forEach(item => {
            const li = document.createElement('li');
            const icon = item.type === 'directory' ? '📁' : '📄';
            li.innerHTML = `<span class="icon">${icon}</span> ${item.name}`;
            li.dataset.path = `${currentPath}/${item.name}`.replace('./', '');
            li.dataset.type = item.type;
            ul.appendChild(li);
        });
        fileBrowser.appendChild(ul);
    }
    
    async function loadFileContent(filepath) {
        try {
            const response = await fetch(`/admin/api/file-content?filepath=${encodeURIComponent(filepath)}`);
            if (!response.ok) throw new Error((await response.json()).error || 'Network error');
            const data = await response.json();
            fileEditor.value = data.content;
            currentOpenFilePath = data.filepath;
            currentFilepathEl.textContent = data.filepath;
            showStatus(fileStatus, `Đã mở file: ${data.filepath}`);
        } catch (error) {
            showStatus(fileStatus, `Lỗi khi mở file: ${error.message}`, true);
        }
    }

    fileBrowser.addEventListener('click', e => {
        const target = e.target.closest('li');
        if (!target) return;
        
        const path = target.dataset.path;
        const type = target.dataset.type;

        if (type === 'directory') {
            loadFileList(path);
        } else if (type === 'file') {
            loadFileContent(path);
        }
    });

    saveFileBtn.addEventListener('click', async () => {
        if (!currentOpenFilePath) {
            showStatus(fileStatus, 'Lỗi: Chưa có file nào được mở.', true);
            return;
        }
        
        const content = fileEditor.value;

        try {
            const response = await fetch('/admin/api/file-content', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ filepath: currentOpenFilePath, content: content }),
            });
            const result = await response.json();
            if (!response.ok) throw new Error(result.error);
            showStatus(fileStatus, result.message || 'Lưu file thành công!');
        } catch (error) {
            showStatus(fileStatus, `Lỗi khi lưu file: ${error.message}`, true);
        }
    });


    // --- INITIAL LOAD ---
    loadConfig();
    loadFileList();
    updateSystemMetrics(); // Lần chạy đầu tiên
    setInterval(updateSystemMetrics, 3000); // Cập nhật mỗi 3 giây
});
