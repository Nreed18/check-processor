// Main JavaScript utilities

// Format currency
function formatCurrency(amount) {
    return new Intl.NumberFormat('en-US', {
        style: 'currency',
        currency: 'USD'
    }).format(amount);
}

// Format date
function formatDate(dateString) {
    const date = new Date(dateString);
    return date.toLocaleDateString('en-US');
}

// Debounce function
function debounce(func, wait) {
    let timeout;
    return function executedFunction(...args) {
        const later = () => {
            clearTimeout(timeout);
            func(...args);
        };
        clearTimeout(timeout);
        timeout = setTimeout(later, wait);
    };
}

// Show notification
function showNotification(message, type = 'info') {
    const notification = document.createElement('div');
    notification.className = `notification notification-${type}`;
    notification.textContent = message;
    
    document.body.appendChild(notification);
    
    setTimeout(() => {
        notification.remove();
    }, 3000);
}

// Global error handler
window.addEventListener('error', (event) => {
    console.error('Application error:', event.error);
});

// Confirm navigation away from unsaved changes
window.addEventListener('beforeunload', (event) => {
    const unsavedChanges = document.querySelectorAll('.edit-field[data-modified="true"]');
    if (unsavedChanges.length > 0) {
        event.preventDefault();
        event.returnValue = '';
    }
});
