// Kairo Phantom — Landing Page Interactions

// Smooth scroll for nav links
document.querySelectorAll('a[href^="#"]').forEach(anchor => {
    anchor.addEventListener('click', function(e) {
        e.preventDefault();
        const target = document.querySelector(this.getAttribute('href'));
        if (target) {
            target.scrollIntoView({ behavior: 'smooth', block: 'start' });
        }
    });
});

// Animate metric values on scroll
const observerOptions = {
    threshold: 0.3,
    rootMargin: '0px 0px -50px 0px'
};

const metricObserver = new IntersectionObserver((entries) => {
    entries.forEach(entry => {
        if (entry.isIntersecting) {
            entry.target.style.opacity = '1';
            entry.target.style.transform = 'translateY(0)';
        }
    });
}, observerOptions);

document.querySelectorAll('.metric-card, .feature-card').forEach(card => {
    card.style.opacity = '0';
    card.style.transform = 'translateY(20px)';
    card.style.transition = 'opacity 0.5s ease, transform 0.5s ease';
    metricObserver.observe(card);
});

// Receipt verification animation
const receiptSection = document.getElementById('receipt');
if (receiptSection) {
    const receiptObserver = new IntersectionObserver((entries) => {
        entries.forEach(entry => {
            if (entry.isIntersecting) {
                const verifyOk = document.querySelector('.verify-ok');
                const verifyFail = document.querySelector('.verify-fail');
                if (verifyOk) {
                    setTimeout(() => verifyOk.style.opacity = '1', 300);
                }
                if (verifyFail) {
                    setTimeout(() => verifyFail.style.opacity = '1', 800);
                }
            }
        });
    }, { threshold: 0.3 });
    receiptObserver.observe(receiptSection);
}
