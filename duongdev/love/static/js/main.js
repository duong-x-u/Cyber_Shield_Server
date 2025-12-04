// Mobile navigation toggle
document.getElementById('navToggle')?.addEventListener('click', function() {
    document.querySelector('.nav-links').classList.toggle('active');
});

// Close mobile nav when clicking outside
document.addEventListener('click', function(e) {
    const navLinks = document.querySelector('.nav-links');
    const navToggle = document.getElementById('navToggle');
    
    if (navLinks?.classList.contains('active') && 
        !navLinks.contains(e.target) && 
        !navToggle.contains(e.target)) {
        navLinks.classList.remove('active');
    }
});

// Smooth scroll for anchor links
document.querySelectorAll('a[href]').forEach(anchor => { // Select all 'a' tags that have an href attribute
    anchor.addEventListener('click', function(e) {
        const href = this.getAttribute('href');
        // Only prevent default and scroll if href starts with # and is not just "#"
        if (href && href.startsWith('#') && href.length > 1) {
            const target = document.querySelector(href);
            if (target) {
                e.preventDefault(); // ONLY prevent default and scroll if it's a valid scroll target
                target.scrollIntoView({
                    behavior: 'smooth',
                    block: 'start'
                });
            }
        }
        // If href is a URL, do not prevent default, let browser navigate normally.
    });
});

// Add animation class when elements come into view
const observerOptions = {
    threshold: 0.1,
    rootMargin: '0px 0px -50px 0px'
};

const observer = new IntersectionObserver((entries) => {
    entries.forEach(entry => {
        if (entry.isIntersecting) {
            entry.target.classList.add('animate-in');
        }
    });
}, observerOptions);

document.querySelectorAll('.dashboard-card, .diary-entry, .gallery-item, .timeline-item').forEach(el => {
    observer.observe(el);
});

// Set current date as default for date inputs
document.querySelectorAll('input[type="date"]').forEach(input => {
    if (!input.value) {
        input.value = new Date().toISOString().split('T')[0];
    }
});

// Add heart animation on click anywhere
document.addEventListener('click', function(e) {
    // Only on hero section or love counter
    const heroSection = document.querySelector('.hero-section');
    if (heroSection?.contains(e.target)) {
        createHeartBurst(e.clientX, e.clientY);
    }
});

function createHeartBurst(x, y) {
    const hearts = ['💕', '💖', '💗', '💓', '💝', '❤️', '💘'];
    
    for (let i = 0; i < 6; i++) {
        const heart = document.createElement('span');
        heart.className = 'burst-heart';
        heart.textContent = hearts[Math.floor(Math.random() * hearts.length)];
        heart.style.cssText = `
            position: fixed;
            left: ${x}px;
            top: ${y}px;
            font-size: ${20 + Math.random() * 20}px;
            pointer-events: none;
            z-index: 9999;
            animation: heartBurst 1s ease-out forwards;
            --tx: ${(Math.random() - 0.5) * 200}px;
            --ty: ${-100 - Math.random() * 100}px;
        `;
        document.body.appendChild(heart);
        
        setTimeout(() => heart.remove(), 1000);
    }
}

// Add CSS for heart burst animation
const style = document.createElement('style');
style.textContent = `
    @keyframes heartBurst {
        0% {
            transform: translate(0, 0) scale(1);
            opacity: 1;
        }
        100% {
            transform: translate(var(--tx), var(--ty)) scale(0);
            opacity: 0;
        }
    }
    
    .animate-in {
        animation: fadeInUp 0.6s ease forwards;
    }
    
    @keyframes fadeInUp {
        from {
            opacity: 0;
            transform: translateY(30px);
        }
        to {
            opacity: 1;
            transform: translateY(0);
        }
    }
`;
document.head.appendChild(style);

console.log('💕 Love Diary loaded successfully!');