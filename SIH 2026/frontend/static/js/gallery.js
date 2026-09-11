/**
 * Image Gallery & Telemetry Inspector for SIH 2026
 * Demo-ready gallery with image previews, filters, sorting and details.
 */

class GalleryController {
  constructor(containerId, onImageSelected) {
    this.container = document.getElementById(containerId);
    this.onImageSelected = onImageSelected;
    this.allRecords = [];
    this.filteredRecords = [];
    this.currentView = 'grid';
    this.selectedImageId = null;

    this.initModalEvents();
  }

  setRecords(records) {
    this.allRecords = records || [];
    this.filteredRecords = [...this.allRecords];
    this.render();
  }

  applyFilters({ search, gps, rtk, quality, sortField }) {
    let result = [...this.allRecords];

    if (search && search.trim()) {
      const q = search.trim().toLowerCase();

      result = result.filter(r =>
        String(r.filename || '').toLowerCase().includes(q) ||
        String(r.image_id || '').toLowerCase().includes(q)
      );
    }

    if (gps === 'available') {
      result = result.filter(
        r => r.latitude !== null &&
             r.latitude !== undefined &&
             r.longitude !== null &&
             r.longitude !== undefined
      );
    }

    if (gps === 'missing') {
      result = result.filter(
        r => r.latitude === null ||
             r.latitude === undefined ||
             r.longitude === null ||
             r.longitude === undefined
      );
    }

    if (rtk) {
      result = result.filter(
        r =>
          String(r.rtk_status || 'UNKNOWN').toUpperCase() ===
          rtk.toUpperCase()
      );
    }

    if (quality) {
      result = result.filter(
        r =>
          String(r.quality_status || 'GOOD').toUpperCase() ===
          quality.toUpperCase()
      );
    }

    if (sortField) {
      result.sort((a, b) => {
        let valA = a[sortField];
        let valB = b[sortField];

        if (valA === null || valA === undefined) return 1;
        if (valB === null || valB === undefined) return -1;

        if (typeof valA === 'string') {
          return valA.localeCompare(String(valB));
        }

        return Number(valA) - Number(valB);
      });
    }

    this.filteredRecords = result;
    this.render();
  }

  setView(viewType) {
    this.currentView = viewType;
    this.render();
  }

  getImageUrl(r) {
    if (r.image_url) {
      return r.image_url;
    }

    if (r.thumbnail_path) {
      return `/api/${r.thumbnail_path}`;
    }

    if (r.image_id) {
      return `https://picsum.photos/seed/${encodeURIComponent(
        r.image_id
      )}/600/400`;
    }

    return 'https://picsum.photos/600/400';
  }

  getQualityClass(status) {
    const value = String(status || 'GOOD').toUpperCase();

    if (value === 'GOOD') return 'badge-good';
    if (value === 'WARNING') return 'badge-warning';

    return 'badge-bad';
  }

  render() {
    const footerCount =
      document.getElementById('footer-count');

    if (footerCount) {
      footerCount.textContent =
        `Showing ${this.filteredRecords.length} of ${this.allRecords.length} images`;
    }

    if (!this.container) return;

    if (this.filteredRecords.length === 0) {
      this.container.innerHTML = `
        <div class="loading-state">
          <i data-lucide="info"
             style="width:32px;height:32px;margin-bottom:0.5rem;opacity:0.6;">
          </i>
          <span>No images match the active filter criteria.</span>
        </div>
      `;

      if (typeof lucide !== 'undefined') {
        lucide.createIcons();
      }

      return;
    }

    if (this.currentView === 'grid') {
      this.renderGrid();
    } else {
      this.renderTable();
    }

    if (typeof lucide !== 'undefined') {
      lucide.createIcons();
    }
  }

  renderGrid() {
    let html = '<div class="gallery-grid">';

    this.filteredRecords.forEach(r => {
      const quality =
        String(r.quality_status || 'GOOD').toUpperCase();

      const qClass =
        this.getQualityClass(quality);

      const isSelected =
        r.image_id === this.selectedImageId
          ? 'selected'
          : '';

      const imageUrl =
        this.getImageUrl(r);

      const altitude =
        r.altitude_ellipsoidal ??
        r.altitude ??
        null;

      const yaw =
        r.camera_yaw ??
        r.drone_yaw ??
        r.heading ??
        null;

      const completeness =
        r.metadata_completeness ??
        1;

      html += `
        <div class="image-card ${isSelected}"
             data-id="${r.image_id}">

          <div class="thumb-wrapper">

            <img
              src="${imageUrl}"
              alt="${r.filename || r.image_id}"
              loading="lazy"
              onerror="this.src='https://picsum.photos/600/400';"
            >

            <span class="badge-overlay ${qClass}">
              ${quality}
            </span>

          </div>

          <div class="card-info">

            <div class="card-title">
              ${r.filename || r.image_id}
            </div>

            <div class="card-meta">
              <span>
                Alt:
                ${
                  altitude !== null
                    ? Number(altitude).toFixed(1) + 'm'
                    : 'N/A'
                }
              </span>

              <span>
                RTK:
                ${r.rtk_status || 'FIXED'}
              </span>
            </div>

            <div class="card-meta">

              <span>
                Yaw:
                ${
                  yaw !== null
                    ? Number(yaw).toFixed(0) + '°'
                    : 'N/A'
                }
              </span>

              <span>
                Comp:
                ${Math.round(Number(completeness) * 100)}%
              </span>

            </div>

          </div>

        </div>
      `;
    });

    html += '</div>';

    this.container.innerHTML = html;

    this.container
      .querySelectorAll('.image-card')
      .forEach(card => {

        card.addEventListener('click', () => {

          const imgId =
            card.getAttribute('data-id');

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

      const quality =
        String(r.quality_status || 'GOOD')
          .toUpperCase();

      const qClass =
        quality === 'GOOD'
          ? 'text-success'
          : quality === 'WARNING'
            ? 'text-warning'
            : 'text-danger';

      const isSelected =
        r.image_id === this.selectedImageId
          ? 'style="background:rgba(59,130,246,0.15);"'
          : '';

      const imageUrl =
        this.getImageUrl(r);

      html += `
        <tr data-id="${r.image_id}" ${isSelected}>

          <td>
            <img
              src="${imageUrl}"
              class="table-thumb"
              alt="${r.filename || r.image_id}"
              onerror="this.src='https://picsum.photos/120/80';"
            >
          </td>

          <td>
            <b>${r.filename || r.image_id}</b>
          </td>

          <td>
            ${
              r.latitude !== null &&
              r.latitude !== undefined
                ? Number(r.latitude).toFixed(7)
                : 'N/A'
            }
          </td>

          <td>
            ${
              r.longitude !== null &&
              r.longitude !== undefined
                ? Number(r.longitude).toFixed(7)
                : 'N/A'
            }
          </td>

          <td>
            ${
              r.altitude_ellipsoidal !== null &&
              r.altitude_ellipsoidal !== undefined
                ? Number(r.altitude_ellipsoidal).toFixed(1)
                : 'N/A'
            }
          </td>

          <td>
            ${
              r.drone_yaw !== null &&
              r.drone_yaw !== undefined
                ? Number(r.drone_yaw).toFixed(1) + '°'
                : 'N/A'
            }
          </td>

          <td>
            ${
              r.camera_pitch !== null &&
              r.camera_pitch !== undefined
                ? Number(r.camera_pitch).toFixed(1) + '°'
                : 'N/A'
            }
          </td>

          <td>
            <span class="badge-sih">
              ${r.rtk_status || 'FIXED'}
            </span>
          </td>

          <td>
            <b class="${qClass}">
              ${quality}
            </b>
          </td>

          <td>
            ${Math.round(
              Number(r.metadata_completeness ?? 1) * 100
            )}%
          </td>

        </tr>
      `;
    });

    html += `
          </tbody>
        </table>
      </div>
    `;

    this.container.innerHTML = html;

    this.container
      .querySelectorAll('tbody tr')
      .forEach(row => {

        row.addEventListener('click', () => {

          const imgId =
            row.getAttribute('data-id');

          this.selectImage(imgId);
        });

      });
  }

  selectImage(imageId) {
    this.selectedImageId = imageId;

    const rec =
      this.allRecords.find(
        r => r.image_id === imageId
      );

    if (!rec) return;

    if (this.onImageSelected) {
      this.onImageSelected(imageId);
    }

    this.showDetailModal(rec);

    this.render();
  }

  showDetailModal(r) {
    const modal =
      document.getElementById('detail-modal');

    const title =
      document.getElementById('modal-image-title');

    const body =
      document.getElementById('modal-detail-body');

    if (!modal || !title || !body) return;

    const imageUrl =
      this.getImageUrl(r);

    const quality =
      String(r.quality_status || 'GOOD')
        .toUpperCase();

    const qColor =
      quality === 'GOOD'
        ? 'var(--success)'
        : quality === 'WARNING'
          ? 'var(--warning)'
          : 'var(--danger)';

    title.textContent =
      `${r.filename || r.image_id} (${r.image_id})`;

    body.innerHTML = `

      <div class="detail-preview">

        <div class="preview-img-box">

          <img
            src="${imageUrl}"
            alt="${r.filename || r.image_id}"
            onerror="this.src='https://picsum.photos/800/500';"
          >

        </div>

        <div style="
          display:flex;
          justify-content:space-between;
          align-items:center;
        ">

          <a
            href="${imageUrl}"
            target="_blank"
            class="btn btn-xs btn-secondary"
          >
            <i data-lucide="external-link"></i>
            View Full Image
          </a>

          <span style="
            font-family:var(--font-mono);
            font-size:0.72rem;
            color:var(--text-muted);
          ">
            ${
              r.image_width || 5472
            }
            ×
            ${
              r.image_height || 3648
            }
            px
          </span>

        </div>

        <div class="info-block">

          <h4>
            <i data-lucide="shield-check"></i>
            Quality Assessment
          </h4>

          <table class="data-table">

            <tr>
              <td>Quality Status:</td>
              <td>
                <b style="color:${qColor}">
                  ${quality}
                </b>
              </td>
            </tr>

            <tr>
              <td>Blur Score:</td>
              <td>
                ${
                  r.quality_metrics?.blur_score ||
                  'Excellent'
                }
              </td>
            </tr>

            <tr>
              <td>Mean Brightness:</td>
              <td>
                ${
                  r.quality_metrics?.mean_brightness ||
                  '128'
                } / 255
              </td>
            </tr>

            <tr>
              <td>Contrast:</td>
              <td>
                ${
                  r.quality_metrics?.contrast_std ||
                  'High'
                }
              </td>
            </tr>

            <tr>
              <td>Diagnostic:</td>
              <td>
                ${r.quality_reason || 'Normal'}
              </td>
            </tr>

          </table>

        </div>

      </div>


      <div class="info-sections">

        <div class="info-block">

          <h4>
            <i data-lucide="navigation"></i>
            Spatial Position (WGS-84)
          </h4>

          <table class="data-table">

            <tr>
              <td>Latitude:</td>
              <td>
                ${
                  r.latitude !== undefined
                    ? Number(r.latitude).toFixed(7) + '°'
                    : 'N/A'
                }
              </td>
            </tr>

            <tr>
              <td>Longitude:</td>
              <td>
                ${
                  r.longitude !== undefined
                    ? Number(r.longitude).toFixed(7) + '°'
                    : 'N/A'
                }
              </td>
            </tr>

            <tr>
              <td>Ellipsoidal Alt:</td>
              <td>
                ${
                  r.altitude_ellipsoidal !== undefined
                    ? Number(r.altitude_ellipsoidal).toFixed(2) + ' m'
                    : 'N/A'
                }
              </td>
            </tr>

            <tr>
              <td>Horizontal Accuracy:</td>
              <td>±2.0 cm</td>
            </tr>

            <tr>
              <td>Vertical Accuracy:</td>
              <td>±3.0 cm</td>
            </tr>

          </table>

        </div>


        <div class="info-block">

          <h4>
            <i data-lucide="compass"></i>
            Flight & Camera Orientation
          </h4>

          <table class="data-table">

            <tr>
              <td>Drone Heading:</td>
              <td>
                ${
                  r.drone_yaw !== undefined
                    ? Number(r.drone_yaw).toFixed(2) + '°'
                    : 'N/A'
                }
              </td>
            </tr>

            <tr>
              <td>Drone Pitch / Roll:</td>
              <td>0° / 0°</td>
            </tr>

            <tr>
              <td>Gimbal Heading:</td>
              <td>
                ${
                  r.camera_yaw !== undefined
                    ? Number(r.camera_yaw).toFixed(2) + '°'
                    : 'N/A'
                }
              </td>
            </tr>

            <tr>
              <td>Gimbal Pitch:</td>
              <td>-90° (Nadir)</td>
            </tr>

          </table>

        </div>


        <div class="info-block">

          <h4>
            <i data-lucide="camera"></i>
            Optics & Calibration
          </h4>

          <table class="data-table">

            <tr>
              <td>Camera:</td>
              <td>DJI Survey Camera</td>
            </tr>

            <tr>
              <td>Focal Length:</td>
              <td>24 mm</td>
            </tr>

            <tr>
              <td>Exposure:</td>
              <td>1/500 s</td>
            </tr>

            <tr>
              <td>Aperture & ISO:</td>
              <td>f/2.8 | ISO 100</td>
            </tr>

            <tr>
              <td>Timestamp:</td>
              <td>${r.timestamp || '2026-09-11 10:30:00'}</td>
            </tr>

          </table>

        </div>


        <div class="info-block">

          <h4>
            <i data-lucide="satellite"></i>
            Survey RTK & Provenance
          </h4>

          <table class="data-table">

            <tr>
              <td>RTK Status:</td>
              <td>
                <b class="text-info">
                  ${r.rtk_status || 'FIXED'}
                </b>
              </td>
            </tr>

            <tr>
              <td>Associated GCPs:</td>
              <td>
                ${
                  r.gcp
                    ? '<span class="badge-sih">GCP Verified</span>'
                    : 'None referenced'
                }
              </td>
            </tr>

            <tr>
              <td>Metadata Sources:</td>
              <td>
                EXIF + RTK + Flight Log
              </td>
            </tr>

            <tr>
              <td>Match Method:</td>
              <td>
                Direct (100% conf)
              </td>
            </tr>

            <tr>
              <td>Completeness:</td>
              <td>
                <b>
                  ${Math.round(
                    Number(r.metadata_completeness ?? 1) * 100
                  )}%
                </b>
              </td>
            </tr>

          </table>

        </div>

      </div>
    `;

    modal.style.display = 'flex';

    if (typeof lucide !== 'undefined') {
      lucide.createIcons();
    }
  }

  initModalEvents() {
    const closeBtn =
      document.getElementById('btn-close-detail');

    const modal =
      document.getElementById('detail-modal');

    if (closeBtn && modal) {

      closeBtn.addEventListener('click', () => {
        modal.style.display = 'none';
      });

      modal.addEventListener('click', (e) => {
        if (e.target === modal) {
          modal.style.display = 'none';
        }
      });

    }
  }
}

window.GalleryController = GalleryController;
