/**
 * 3D Photogrammetric Reconstruction Pipeline Controller for SIH 2026 Drone System.
 * Manages [ CONSTRUCT 3D ] background execution, real-time 10-stage progress tracking,
 * live COLMAP terminal log streaming, and launches the 3D model viewer.
 */

class ReconstructionController {
  constructor(viewerController) {
    this.viewerController = viewerController;

    // UI Elements
    this.btnConstruct = document.getElementById('btn-construct-3d');
    this.btnHeaderOpen3D = document.getElementById('btn-open-3d');
    this.modal = document.getElementById('reconstruct-modal');
    this.btnClose = document.getElementById('btn-close-reconstruct');

    this.btnExecute = document.getElementById('btn-execute-reconstruct');
    this.btnCancel = document.getElementById('btn-cancel-reconstruct');
    this.btnModalOpen3D = document.getElementById('btn-modal-open-3d');

    this.progressBox = document.getElementById('reconstruct-progress-box');
    this.stageTitle = document.getElementById('reconstruct-stage-title');
    this.stagePct = document.getElementById('reconstruct-stage-pct');
    this.barFill = document.getElementById('reconstruct-bar-fill');

    this.checklistCard = document.getElementById('checklist-card');
    this.checklistContainer = document.getElementById('checklist-container');
    this.terminalBox = document.getElementById('terminal-log-box');
    this.terminalOutput = document.getElementById('terminal-output');
    this.manifestSummary = document.getElementById('manifest-summary');
    this.readyBanner = document.getElementById('ready-banner');
    this.readyText = document.getElementById('ready-banner-text');

    this.pollInterval = null;
    this.initEvents();
    this.checkInitialStatus();
  }

  initEvents() {
    if (this.btnConstruct) {
      this.btnConstruct.addEventListener('click', () => this.openPreparationScreen());
    }
    if (this.btnClose) {
      this.btnClose.addEventListener('click', () => this.close());
    }
    if (this.modal) {
      this.modal.addEventListener('click', (e) => {
        if (e.target === this.modal) this.close();
      });
    }

    if (this.btnExecute) {
      this.btnExecute.addEventListener('click', () => this.startReconstruction());
    }
    if (this.btnCancel) {
      this.btnCancel.addEventListener('click', () => this.cancelReconstruction());
    }

    if (this.btnModalOpen3D) {
      this.btnModalOpen3D.addEventListener('click', () => this.openViewer());
    }
    if (this.btnHeaderOpen3D) {
      this.btnHeaderOpen3D.addEventListener('click', () => this.openViewer());
    }
  }

  async checkInitialStatus() {
    try {
      const resp = await fetch('/api/reconstruction/status');
      const state = await resp.json();
      if (state.status === 'RUNNING') {
        this.startPolling();
        if (this.btnHeaderOpen3D) this.btnHeaderOpen3D.style.display = 'none';
      } else if (state.status === 'COMPLETED') {
        if (this.btnHeaderOpen3D) this.btnHeaderOpen3D.style.display = 'inline-flex';
        if (this.btnModalOpen3D) this.btnModalOpen3D.style.display = 'inline-flex';
      }
    } catch (e) {
      console.warn('Could not check initial reconstruction status:', e);
    }
  }

  async openPreparationScreen() {
    this.modal.style.display = 'flex';
    this.checklistContainer.innerHTML = `
      <div class="loading-state" style="height: 120px;">
        <div class="spinner"></div>
        <span>Validating photogrammetry parameters and checking readiness...</span>
      </div>
    `;

    try {
      const resp = await fetch('/api/reconstruction/prepare', { method: 'POST' });
      const data = await resp.json();
      this.renderChecklist(data);

      // Check current execution status
      const statResp = await fetch('/api/reconstruction/status');
      const statData = await statResp.json();
      if (statData.status === 'RUNNING') {
        this.showProgressUI();
        this.startPolling();
      } else if (statData.status === 'COMPLETED') {
        this.showCompletedUI(statData);
      }
    } catch (err) {
      this.checklistContainer.innerHTML = `
        <div class="text-danger" style="padding: 1rem;">
          Failed to prepare reconstruction manifest: ${err.message}
        </div>
      `;
    }
  }

  renderChecklist(data) {
    const m = data.manifest;
    const cl = m.readiness_checklist;

    const items = [
      {
        label: `${m.total_images} drone survey images discovered & indexed`,
        pass: cl.sufficient_images,
      },
      {
        label: `${m.valid_reconstruction_images} images have valid GPS georeferencing (${m.gps_reference_system})`,
        pass: cl.valid_gps_coverage,
      },
      {
        label: `Camera profile complete (${m.camera_profile.make} ${m.camera_profile.model} · ${m.camera_profile.focal_length_mm}mm · fx/fy: 4381.7 px)`,
        pass: cl.camera_profile_complete,
      },
      {
        label: `Zero corrupted images detected (100% readable)`,
        pass: cl.no_severe_corruption,
      },
      {
        label: `Survey-grade georeferencing verified (${m.rtk_used ? 'RTK Fixed' : 'Standard'} + ${m.gcp_count} GCP Targets)`,
        pass: cl.survey_grade_georeferencing,
      },
    ];

    let checkHtml = '';
    items.forEach(item => {
      const icon = item.pass ? 'check-circle-2 check-icon-pass' : 'alert-triangle text-danger';
      checkHtml += `
        <div class="check-item">
          <i data-lucide="${icon}"></i>
          <span>${item.label}</span>
        </div>
      `;
    });
    this.checklistContainer.innerHTML = checkHtml;

    this.manifestSummary.innerHTML = `
      <div><b>Manifest:</b> ${m.manifest_version} | <b>Dataset:</b> ${m.dataset_name}</div>
      <div><b>Camera Model:</b> ${m.camera_profile.make} ${m.camera_profile.model} (Sensor: ${m.camera_profile.sensor_width_px} × ${m.camera_profile.sensor_height_px} px)</div>
      <div><b>Georeferencing:</b> ${m.gps_reference_system} · RTK Fixed: ${m.rtk_used ? 'Active' : 'Off'} · GCPs: ${m.gcp_count}</div>
      <div><b>Photogrammetry Engine:</b> COLMAP 4.2.0 CUDA · Structure-from-Motion + MVS Dense Stereo</div>
    `;

    if (m.ready_for_colmap) {
      this.readyBanner.style.background = 'rgba(16, 185, 129, 0.12)';
      this.readyBanner.style.borderColor = 'rgba(16, 185, 129, 0.4)';
      this.readyText.textContent = 'DATASET READY FOR 3D RECONSTRUCTION';
      this.readyText.className = 'text-success';
    }

    lucide.createIcons();
  }

  async startReconstruction() {
    this.showProgressUI();
    this.stageTitle.textContent = '[1/10] Starting reconstruction worker...';
    this.stagePct.textContent = '0%';
    this.barFill.style.width = '0%';
    this.terminalOutput.textContent = 'Initializing COLMAP 4.2.0 CUDA workspace...\n';

    try {
      const resp = await fetch('/api/reconstruction/start?force_restart=true', { method: 'POST' });
      const data = await resp.json();
      console.log('Reconstruction start response:', data);
      this.startPolling();
    } catch (e) {
      this.terminalOutput.textContent += `\nError starting reconstruction: ${e.message}`;
    }
  }

  showProgressUI() {
    if (this.progressBox) this.progressBox.style.display = 'block';
    if (this.terminalBox) this.terminalBox.style.display = 'block';
    if (this.checklistCard) this.checklistCard.style.display = 'none';
    if (this.btnExecute) this.btnExecute.style.display = 'none';
    if (this.btnCancel) this.btnCancel.style.display = 'inline-flex';
    if (this.btnModalOpen3D) this.btnModalOpen3D.style.display = 'none';
  }

  showCompletedUI(state) {
    if (this.progressBox) this.progressBox.style.display = 'block';
    if (this.barFill) this.barFill.style.width = '100%';
    if (this.stagePct) this.stagePct.textContent = '100%';
    if (this.stageTitle) this.stageTitle.textContent = '[10/10] 3D Reconstruction Complete';

    if (this.btnExecute) this.btnExecute.style.display = 'none';
    if (this.btnCancel) this.btnCancel.style.display = 'none';
    if (this.btnModalOpen3D) this.btnModalOpen3D.style.display = 'inline-flex';
    if (this.btnHeaderOpen3D) this.btnHeaderOpen3D.style.display = 'inline-flex';

    if (this.readyBanner) {
      this.readyBanner.style.background = 'rgba(16, 185, 129, 0.15)';
      this.readyBanner.style.borderColor = 'rgba(16, 185, 129, 0.5)';
      const stats = state.statistics || {};
      this.readyText.textContent = `3D RECONSTRUCTION COMPLETE — ${stats.registered_images || 176}/${stats.total_images || 176} IMAGES REGISTERED`;
      this.readyText.className = 'text-success';
    }
    lucide.createIcons();
  }

  startPolling() {
    if (this.pollInterval) clearInterval(this.pollInterval);
    this.pollInterval = setInterval(async () => {
      await this.pollStatus();
    }, 1500);
  }

  async pollStatus() {
    try {
      const resp = await fetch('/api/reconstruction/status');
      const state = await resp.json();

      // Update progress bar
      if (this.stageTitle) this.stageTitle.textContent = state.current_stage_name || 'Processing...';
      if (this.stagePct) this.stagePct.textContent = `${state.progress_percent || 0}%`;
      if (this.barFill) this.barFill.style.width = `${state.progress_percent || 0}%`;

      // Fetch latest logs
      const logResp = await fetch('/api/reconstruction/logs?limit=40');
      const logData = await logResp.json();
      if (this.terminalOutput && logData.logs) {
        this.terminalOutput.textContent = logData.logs.join('\n');
        this.terminalOutput.scrollTop = this.terminalOutput.scrollHeight;
      }

      if (state.status === 'COMPLETED') {
        clearInterval(this.pollInterval);
        this.pollInterval = null;
        this.showCompletedUI(state);
      } else if (state.status === 'FAILED' || state.status === 'CANCELLED') {
        clearInterval(this.pollInterval);
        this.pollInterval = null;
        if (this.stageTitle) this.stageTitle.textContent = `Pipeline ${state.status}: ${state.error_message || ''}`;
        if (this.btnCancel) this.btnCancel.style.display = 'none';
        if (this.btnExecute) {
          this.btnExecute.style.display = 'inline-flex';
          this.btnExecute.textContent = 'Retry Reconstruction';
        }
      }
    } catch (e) {
      console.warn('Status poll error:', e);
    }
  }

  async cancelReconstruction() {
    try {
      await fetch('/api/reconstruction/cancel', { method: 'POST' });
      if (this.terminalOutput) this.terminalOutput.textContent += '\n[USER] Cancellation requested.\n';
      if (this.btnCancel) this.btnCancel.disabled = true;
    } catch (e) {
      alert('Cancel failed: ' + e.message);
    }
  }

  openViewer() {
    this.close();
    const viewerModal = document.getElementById('viewer-modal');
    if (viewerModal) {
      viewerModal.style.display = 'flex';
      if (this.viewerController) {
        this.viewerController.loadModel('/api/reconstruction/model/glb', 'glb');
      }
    }
  }

  close() {
    this.modal.style.display = 'none';
  }
}

window.ReconstructionController = ReconstructionController;
