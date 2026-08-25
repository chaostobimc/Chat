/**
 * Discord Ticket Bot - Dashboard JavaScript
 */

// Update time
function updateTime() {
    const timeEl = document.getElementById('current-time');
    if (timeEl) {
        const now = new Date();
        const options = { 
            weekday: 'short', 
            day: '2-digit', 
            month: 'short',
            hour: '2-digit', 
            minute: '2-digit'
        };
        timeEl.textContent = now.toLocaleDateString('de-DE', options);
    }
}

updateTime();
setInterval(updateTime, 60000);

// Mobile sidebar toggle
function toggleSidebar() {
    const sidebar = document.querySelector('.sidebar');
    if (sidebar) {
        sidebar.classList.toggle('active');
    }
}

// Close sidebar when clicking outside on mobile
document.addEventListener('click', function(event) {
    const sidebar = document.querySelector('.sidebar');
    const toggle = document.querySelector('.mobile-toggle');
    
    if (sidebar && toggle) {
        if (!sidebar.contains(event.target) && !toggle.contains(event.target)) {
            sidebar.classList.remove('active');
        }
    }
});

// Modal functions
function showModal(modalId) {
    const modal = document.getElementById(modalId);
    if (modal) {
        modal.classList.add('active');
        document.body.style.overflow = 'hidden';
    }
}

function hideModal(modalId) {
    const modal = document.getElementById(modalId);
    if (modal) {
        modal.classList.remove('active');
        document.body.style.overflow = '';
    }
}

// Close modal on backdrop click
document.addEventListener('click', function(event) {
    if (event.target.classList.contains('modal-backdrop')) {
        const modal = event.target.closest('.modal');
        if (modal) {
            modal.classList.remove('active');
            document.body.style.overflow = '';
        }
    }
});

// Close modal on Escape key
document.addEventListener('keydown', function(event) {
    if (event.key === 'Escape') {
        const activeModals = document.querySelectorAll('.modal.active');
        activeModals.forEach(modal => {
            modal.classList.remove('active');
        });
        document.body.style.overflow = '';
    }
});

// Form validation
document.querySelectorAll('form').forEach(form => {
    form.addEventListener('submit', function(event) {
        // Update modal fields JSON before submit
        updateModalFieldsJSON();
        
        const requiredInputs = form.querySelectorAll('[required]');
        let isValid = true;
        
        requiredInputs.forEach(input => {
            if (!input.value.trim()) {
                isValid = false;
                input.classList.add('error');
            } else {
                input.classList.remove('error');
            }
        });
        
        if (!isValid) {
            event.preventDefault();
            showNotification('Bitte fülle alle Pflichtfelder aus.', 'error');
        }
    });
});

// Modal Fields Management
function toggleModalFields() {
    const useModalCheckbox = document.getElementById('use_modal');
    const modalFieldsSection = document.getElementById('modal_fields_section');
    const requireQuestionCheckbox = document.getElementById('require_question');
    
    if (useModalCheckbox && modalFieldsSection) {
        if (useModalCheckbox.checked) {
            modalFieldsSection.classList.remove('hidden');
            if (requireQuestionCheckbox) {
                requireQuestionCheckbox.checked = false;
            }
        } else {
            modalFieldsSection.classList.add('hidden');
        }
    }
}

function addField() {
    const fieldsList = document.getElementById('modal_fields_list');
    if (!fieldsList) return;
    
    const fieldItem = document.createElement('div');
    fieldItem.className = 'modal-field-item';
    fieldItem.innerHTML = `
        <div class="field-row">
            <input type="text" name="field_label" placeholder="Feldname (z.B. Discord-Tag)" class="field-input">
            <select name="field_style" class="field-input">
                <option value="short">Kurztext</option>
                <option value="paragraph">Langtext</option>
            </select>
            <input type="text" name="field_placeholder" placeholder="Platzhalter..." class="field-input">
            <label class="field-required-toggle">
                <input type="checkbox" name="field_required" checked>
                <span>Pflichtfeld</span>
            </label>
            <button type="button" class="btn-remove-field" onclick="removeField(this)">
                <i class="fas fa-times"></i>
            </button>
        </div>
    `;
    fieldsList.appendChild(fieldItem);
}

function removeField(button) {
    const fieldItem = button.closest('.modal-field-item');
    const fieldsList = document.getElementById('modal_fields_list');
    
    if (fieldsList && fieldsList.children.length > 1) {
        fieldItem.remove();
    } else {
        showNotification('Du musst mindestens ein Feld haben!', 'error');
    }
}

function updateModalFieldsJSON() {
    const fieldsList = document.getElementById('modal_fields_list');
    const jsonInput = document.getElementById('modal_fields_json');
    
    if (!fieldsList || !jsonInput) return;
    
    const fields = [];
    const fieldItems = fieldsList.querySelectorAll('.modal-field-item');
    
    fieldItems.forEach(item => {
        const label = item.querySelector('input[name="field_label"]').value.trim();
        const style = item.querySelector('select[name="field_style"]').value;
        const placeholder = item.querySelector('input[name="field_placeholder"]').value.trim();
        const required = item.querySelector('input[name="field_required"]').checked;
        
        if (label) {
            fields.push({
                label: label,
                style: style,
                placeholder: placeholder,
                required: required
            });
        }
    });
    
    jsonInput.value = JSON.stringify(fields);
}

// Input error styling
document.querySelectorAll('input, select, textarea').forEach(input => {
    input.addEventListener('input', function() {
        if (this.value.trim()) {
            this.classList.remove('error');
        }
    });
});

// Notification system
function showNotification(message, type = 'success') {
    const notification = document.createElement('div');
    notification.className = `alert alert-${type}`;
    notification.innerHTML = `
        <i class="fas fa-${type === 'success' ? 'check-circle' : 'exclamation-circle'}"></i>
        ${message}
        <button class="alert-close" onclick="this.parentElement.remove()">
            <i class="fas fa-times"></i>
        </button>
    `;
    
    // Find or create alerts container
    let alertsContainer = document.querySelector('.alerts');
    if (!alertsContainer) {
        alertsContainer = document.createElement('div');
        alertsContainer.className = 'alerts';
        const contentArea = document.querySelector('.content-area');
        if (contentArea) {
            contentArea.insertBefore(alertsContainer, contentArea.firstChild);
        }
    }
    
    alertsContainer.appendChild(notification);
    
    // Auto-remove after 5 seconds
    setTimeout(() => {
        if (notification.parentElement) {
            notification.remove();
        }
    }, 5000);
}

// Confirm delete actions
document.querySelectorAll('form[onsubmit]').forEach(form => {
    form.addEventListener('submit', function(event) {
        const submitBtn = form.querySelector('button[type="submit"]');
        if (submitBtn && submitBtn.classList.contains('btn-danger')) {
            if (!confirm('Bist du sicher, dass du diesen Eintrag löschen möchtest?')) {
                event.preventDefault();
            }
        }
    });
});

// Live preview for button label
const labelInput = document.getElementById('label');
const previewBtn = document.getElementById('buttonPreview');

if (labelInput && previewBtn) {
    labelInput.addEventListener('input', function() {
        const emoji = document.getElementById('emoji');
        previewBtn.textContent = (emoji ? emoji.value : '') + ' ' + (this.value || 'Button Text');
    });
}

// Copy to clipboard
function copyToClipboard(text) {
    navigator.clipboard.writeText(text).then(() => {
        showNotification('In die Zwischenablage kopiert!', 'success');
    }).catch(err => {
        console.error('Copy failed:', err);
    });
}

// API stats refresh
async function refreshStats() {
    try {
        const response = await fetch('/api/stats');
        const stats = await response.json();
        
        // Update stat numbers if they exist on page
        const totalEl = document.querySelector('.stat-total .stat-number');
        const openEl = document.querySelector('.stat-open .stat-number');
        const closedEl = document.querySelector('.stat-closed .stat-number');
        
        if (totalEl) totalEl.textContent = stats.total || 0;
        if (openEl) openEl.textContent = stats.open || 0;
        if (closedEl) closedEl.textContent = stats.closed || 0;
        
    } catch (error) {
        console.error('Failed to fetch stats:', error);
    }
}

// Auto-refresh stats every 30 seconds on dashboard
if (window.location.pathname === '/dashboard') {
    refreshStats();
    setInterval(refreshStats, 30000);
}

// Initialize tooltips for elements with title attribute
document.querySelectorAll('[title]').forEach(el => {
    el.setAttribute('data-tooltip', el.getAttribute('title'));
});

// Handle select dropdown styling
document.querySelectorAll('select').forEach(select => {
    select.addEventListener('change', function() {
        if (this.value) {
            this.classList.add('has-value');
        } else {
            this.classList.remove('has-value');
        }
    });
    
    // Initial check
    if (select.value) {
        select.classList.add('has-value');
    }
});

// Table row hover effect
document.querySelectorAll('.tickets-table tbody tr').forEach(row => {
    row.addEventListener('click', function() {
        const link = this.querySelector('a');
        if (link) {
            window.location.href = link.href;
        }
    });
    
    row.style.cursor = 'pointer';
});

// Panel/Button toggle switches
document.querySelectorAll('.toggle-switch').forEach(toggle => {
    toggle.addEventListener('change', function() {
        const form = this.closest('form');
        if (form) {
            form.submit();
        }
    });
});

// Smooth scroll for anchor links
document.querySelectorAll('a[href^="#"]').forEach(anchor => {
    anchor.addEventListener('click', function(e) {
        const targetId = this.getAttribute('href');
        if (targetId !== '#') {
            e.preventDefault();
            const target = document.querySelector(targetId);
            if (target) {
                target.scrollIntoView({ behavior: 'smooth' });
            }
        }
    });
});

// Export functionality placeholder
function exportData(type) {
    showNotification(`${type} Export wird vorbereitet...`, 'success');
    // Implementation would go here
}

// Print page
function printPage() {
    window.print();
}

// Initialize modal fields on page load
document.addEventListener('DOMContentLoaded', function() {
    const useModalCheckbox = document.getElementById('use_modal');
    if (useModalCheckbox && !useModalCheckbox.checked) {
        const modalFieldsSection = document.getElementById('modal_fields_section');
        if (modalFieldsSection) {
            modalFieldsSection.classList.add('hidden');
        }
    }
});
