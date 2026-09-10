/**
 * Image Gallery & Telemetry Inspector for SIH 2026 Drone Ingestion System.
 * Supports Grid & Table views, real-time filtering, sorting, and full detail modal.
 */

class GalleryController {
  constructor(containerId, onImageSelected) {
    this.container = document.getElementById(containerId);
    this.onImageSelected = onImageSelected;
    this.allRecords = [];
    this.filteredRecords = [];
    this.currentView = 'grid'; // 'grid' or 'table'
    this.selectedImageId = null;

    this.initModalEvents();
  }

  setRecords(records) {
    this.allRecords = records;
    this.filteredRecords = [...records];
    this.render();
  }

  applyFilters({ search, gps, rtk, quality, sortField }) {
    let result = [...this.allRecords];

    // Search filter (filename or image_id)
    if (search && search.trim()) {
      const q = search.trim().toLowerCase();
      result = result.filter(r =>
        r.filename.toLowerCase().includes(q) || r.image_id.toLowerCase().includes(q)
      );
    }

    // GPS filter
    if (gps === 'available') {
      result = result.filter(r => r.latitude !== null && r.longitude !== null);
    } else if (gps === 'missing') {
      result = result.filter(r => r.latitude === null || r.longitude === null);
    }

    // RTK filter
    if (rtk) {
      result = result.filter(r => (r.rtk_status || '').toUpperCase() === rtk.toUpperCase());
    }

    // Quality filter
    if (quality) {
      result = result.filter(r => (r.quality_status || '').toUpperCase() === quality.toUpperCase());
    }

    // Sorting
    if (sortField) {
      result.sort((a, b) => {
        let valA = a[sortField];
        let valB = b[sortField];
        if (valA === null || valA === undefined) return 1;
        if (valB === null || valB === undefined) return -1;
        if (typeof valA === 'string') return valA.localeCompare(valB);
        return valA - valB;
      });
    }

    this.filteredRecords = result;
    this.render();
  }

  setView(viewType) {
    this.currentView = viewType;
    this.render();
  }

  render() {
    const footerCount = document.getElementById('footer-count');
    if (footerCount) {
      footerCount.textContent = `Showing ${this.filteredRecords.length} of ${this.allRecords.length} images`;
    }

    if (this.filteredRecords.length === 0) {
      this.container.innerHTML = `
        <div class="loading-state">
          <i data-lucide="info" style="width: 32px; height: 32px; margin-bottom: 0.5rem; opacity: 0.6;"></i>
          <span>No images match the active filter criteria.</span>
        </div>
      `;
      lucide.createIcons();
      return;
    }

    if (this.currentView === 'grid') {
      this.renderGrid();
    } else {
      this.renderTable();
    }
    lucide.createIcons();
  }

  renderGrid() {
    let html = '<div class="gallery-grid">';
    this.filteredRecords.forEach(r => {
      const qClass = r.quality_status === 'GOOD' ? 'badge-good' : (r.quality_status === 'WARNING' ? 'badge-warning' : 'badge-bad');
      const isSelected = r.image_id === this.selectedImageId ? 'selected' : '';
      const thumbUrl = r.thumbnail_path ? `/api/${r.thumbnail_path}` : `/api/images/${r.image_id}/full`;

      html += `
        <div class="image-card ${isSelected}" data-id="${r.image_id}">
          <div class="thumb-wrapper">
            <img src="${thumbUrl}" alt="${r.filename}" loading="lazy">
            <span class="badge-overlay ${qClass}">${r.quality_status}</span>
          </div>
          <div class="card-info">
            <div class="card-title">${r.filename}</div>
            <div class="card-meta">
              <span>Alt: ${r.altitude_ellipsoidal ? r.altitude_ellipsoidal.toFixed(1) + 'm' : 'N/A'}</span>
              <span>RTK: ${r.rtk_status || 'UNKNOWN'}</span>
            </div>
            <div class="card-meta">
              <span>Yaw: ${r.camera_yaw !== null && r.camera_yaw !== undefined ? r.camera_yaw.toFixed(0) + '°' : (r.drone_yaw !== null && r.drone_yaw !== undefined ? r.drone_yaw.toFixed(0) + '°' : 'N/A')}</span>
              <span>Comp: ${Math.round((r.metadata_completeness || 0) * 100)}%</span>
            </div>
          </div>
        </div>
      `;
    });
    html += '</div>';
    this.container.innerHTML = html;

    // Attach click handlers
    this.container.querySelectorAll('.image-card').forEach(card => {
      card.addEventListener('click', () => {
        const imgId = card.getAttribute('data-id');
        this.selectImage(imgId);
      });
    });
  }

  renderTable() {
    let html = `
      <div class="table-view-container">
        <table class="telemetry-table">
          <thead>
            <tr>
              <th>Preview</th>
              <th>Filename</th>
              <th>Latitude</th>
              <th>Longitude</th>
              <th>Alt (m)</th>
              <th>Heading</th>
              <th>Gimbal Pitch</th>
              <th>RTK Status</th>
              <th>Quality</th>
              <th>Completeness</th>
            </tr>
          </thead>
          <tbody>
    `;

    this.filteredRecords.forEach(r => {
      const qClass = r.quality_status === 'GOOD' ? 'text-success' : (r.quality_status === 'WARNING' ? 'text-warning' : 'text-danger');
      const isSelected = r.image_id === this.selectedImageId ? 'style="background: rgba(59,130,246,0.15);"' : '';
      const thumbUrl = r.thumbnail_path ? `/api/${r.thumbnail_path}` : `/api/images/${r.image_id}/full`;

      html += `
        <tr data-id="${r.image_id}" ${isSelected}>
          <td><img src="${thumbUrl}" class="table-thumb" alt="${r.filename}"></td>
          <td><b>${r.filename}</b></td>
          <td>${r.latitude ? r.latitude.toFixed(7) : 'N/A'}</td>
          <td>${r.longitude ? r.longitude.toFixed(7) : 'N/A'}</td>
          <td>${r.altitude_ellipsoidal ? r.altitude_ellipsoidal.toFixed(1) : 'N/A'}</td>
          <td>${r.drone_yaw !== null && r.drone_yaw !== undefined ? r.drone_yaw.toFixed(1) + '°' : 'N/A'}</td>
          <td>${r.camera_pitch !== null && r.camera_pitch !== undefined ? r.camera_pitch.toFixed(1) + '°' : 'N/A'}</td>
          <td><span class="badge-sih">${r.rtk_status || 'UNKNOWN'}</span></td>
          <td><b class="${qClass}">${r.quality_status}</b></td>
          <td>${Math.round((r.metadata_completeness || 0) * 100)}%</td>
        </tr>
      `;
    });

    html += `
          </tbody>
        </table>
      </div>
    `;
    this.container.innerHTML = html;

    this.container.querySelectorAll('tbody tr').forEach(row => {
      row.addEventListener('click', () => {
        const imgId = row.getAttribute('data-id');
        this.selectImage(imgId);
      });
    });
  }

  selectImage(imageId) {
    this.selectedImageId = imageId;
    const rec = this.allRecords.find(r => r.image_id === imageId);
    if (!rec) return;

    if (this.onImageSelected) {
      this.onImageSelected(imageId);
    }
    this.showDetailModal(rec);
  }

  showDetailModal(r) {
    const modal = document.getElementById('detail-modal');
    const title = document.getElementById('modal-image-title');
    const body = document.getElementById('modal-detail-body');

    title.textContent = `${r.filename} (${r.image_id})`;
    const fullImgUrl = `/api/images/${r.image_id}/full`;
    const qColor = r.quality_status === 'GOOD' ? 'var(--success)' : (r.quality_status === 'WARNING' ? 'var(--warning)' : 'var(--danger)');

    body.innerHTML = `
      <div class="detail-preview">
        <div class="preview-img-box">
          <img src="${fullImgUrl}" alt="${r.filename}">
        </div>
        <div style="display: flex; justify-content: space-between; align-items: center;">
          <a href="${fullImgUrl}" target="_blank" class="btn btn-xs btn-secondary">
            <i data-lucide="external-link"></i> View Full 20MP Image
          </a>
          <span style="font-family: var(--font-mono); font-size: 0.72rem; color: var(--text-muted);">
            ${r.image_width} × ${r.image_height} px (${(r.filesize_bytes / (1024 * 1024)).toFixed(1)} MB)
          </span>
        </div>

        <div class="info-block">
          <h4><i data-lucide="shield-check"></i> Quality Assessment</h4>
          <table class="data-table">
            <tr><td>Quality Status:</td><td><b style="color: ${qColor};">${r.quality_status}</b></td></tr>
            <tr><td>Blur Score:</td><td>${r.quality_metrics ? r.quality_metrics.blur_score : 'N/A'} (Laplacian var)</td></tr>
            <tr><td>Mean Brightness:</td><td>${r.quality_metrics ? r.quality_metrics.mean_brightness : 'N/A'} / 255</td></tr>
            <tr><td>Contrast (Std):</td><td>${r.quality_metrics ? r.quality_metrics.contrast_std : 'N/A'}</td></tr>
            <tr><td>Diagnostic:</td><td>${r.quality_reason || 'Normal'}</td></tr>
            <tr><td>MD5 Hash:</td><td style="font-size: 0.65rem;">${r.quality_metrics && r.quality_metrics.file_hash_md5 ? r.quality_metrics.file_hash_md5 : 'N/A'}</td></tr>
          </table>
        </div>
      </div>

      <div class="info-sections">
        <div class="info-block">
          <h4><i data-lucide="navigation"></i> Spatial Position (WGS-84)</h4>
          <table class="data-table">
            <tr><td>Latitude:</td><td>${r.latitude ? r.latitude.toFixed(9) + '°' : 'N/A'}</td></tr>
            <tr><td>Longitude:</td><td>${r.longitude ? r.longitude.toFixed(9) + '°' : 'N/A'}</td></tr>
            <tr><td>Ellipsoidal Alt:</td><td>${r.altitude_ellipsoidal ? r.altitude_ellipsoidal.toFixed(3) + ' m' : 'N/A'}</td></tr>
            <tr><td>Relative Alt (AGL):</td><td>${r.altitude_relative ? r.altitude_relative.toFixed(2) + ' m' : 'N/A'}</td></tr>
            <tr><td>Horizontal Accuracy:</td><td>${r.gps_accuracy_h ? '±' + (r.gps_accuracy_h * 100).toFixed(1) + ' cm' : 'N/A'}</td></tr>
            <tr><td>Vertical Accuracy:</td><td>${r.gps_accuracy_v ? '±' + (r.gps_accuracy_v * 100).toFixed(1) + ' cm' : 'N/A'}</td></tr>
          </table>
        </div>

        <div class="info-block">
          <h4><i data-lucide="compass"></i> Flight & Camera Orientation</h4>
          <table class="data-table">
            <tr><td>Drone Heading (Yaw):</td><td>${r.drone_yaw !== null && r.drone_yaw !== undefined ? r.drone_yaw.toFixed(2) + '°' : 'N/A'}</td></tr>
            <tr><td>Drone Pitch / Roll:</td><td>${r.drone_pitch !== null ? r.drone_pitch.toFixed(1) + '°' : '0°'} / ${r.drone_roll !== null ? r.drone_roll.toFixed(1) + '°' : '0°'}</td></tr>
            <tr><td>Gimbal Heading (Yaw):</td><td>${r.camera_yaw !== null && r.camera_yaw !== undefined ? r.camera_yaw.toFixed(2) + '°' : 'N/A'}</td></tr>
            <tr><td>Gimbal Pitch (Angle):</td><td>${r.camera_pitch !== null && r.camera_pitch !== undefined ? r.camera_pitch.toFixed(2) + '° (Nadir)' : 'N/A'}</td></tr>
          </table>
        </div>

        <div class="info-block">
          <h4><i data-lucide="camera"></i> Optics & Calibration</h4>
          <table class="data-table">
            <tr><td>Camera:</td><td>${r.camera_make || ''} ${r.camera_model || 'Unknown'}</td></tr>
            <tr><td>Focal Length:</td><td>${r.focal_length_mm ? r.focal_length_mm + ' mm' : 'N/A'} (35mm equiv: ${r.focal_length_35mm ? r.focal_length_35mm + ' mm' : 'N/A'})</td></tr>
            <tr><td>Exposure / Shutter:</td><td>${r.exposure_time_s ? '1/' + Math.round(1/r.exposure_time_s) + ' s' : 'N/A'}</td></tr>
            <tr><td>Aperture & ISO:</td><td>f/${r.aperture_fnumber || 'N/A'} | ISO ${r.iso || 'N/A'}</td></tr>
            <tr><td>Timestamp:</td><td>${r.timestamp || 'N/A'}</td></tr>
          </table>
        </div>

        <div class="info-block">
          <h4><i data-lucide="satellite"></i> Survey RTK & Provenance</h4>
          <table class="data-table">
            <tr><td>RTK Status:</td><td><b class="text-info">${r.rtk_status} (Code: ${r.rtk_flag || 'N/A'})</b></td></tr>
            <tr><td>Associated GCPs:</td><td>${r.associated_gcps && r.associated_gcps.length > 0 ? r.associated_gcps.map(g => `<span class="badge-sih" style="background: rgba(236,72,153,0.2); color: #EC4899;">GCP ${g}</span>`).join(' ') : 'None referenced'}</td></tr>
            <tr><td>Metadata Sources:</td><td>${(r.metadata_sources || []).join(' + ')}</td></tr>
            <tr><td>Match Method:</td><td>${r.match_method || 'Direct'} (${Math.round((r.match_confidence || 1) * 100)}% conf)</td></tr>
            <tr><td>Completeness:</td><td><b>${Math.round((r.metadata_completeness || 0) * 100)}%</b></td></tr>
          </table>
        </div>
      </div>
    `;

    modal.style.display = 'flex';
    lucide.createIcons();
  }

  initModalEvents() {
    const closeBtn = document.getElementById('btn-close-detail');
    const modal = document.getElementById('detail-modal');

    if (closeBtn && modal) {
      closeBtn.addEventListener('click', () => {
        modal.style.display = 'none';
      });
      modal.addEventListener('click', (e) => {
        if (e.target === modal) modal.style.display = 'none';
      });
    }
  }
}

window.GalleryController = GalleryController;
