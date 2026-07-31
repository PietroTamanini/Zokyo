/* ============================================
   DJ TECH - JAVASCRIPT INTERATIVO
   ============================================ */

document.addEventListener('DOMContentLoaded', function() {



    // Listener para scroll
    window.addEventListener('scroll', handleNavbarScroll);

    // ============================================
    // SMOOTH SCROLL PARA LINKS INTERNOS
    // ============================================

    const navLinks = document.querySelectorAll('a[href^="#"]');

    navLinks.forEach(link => {
        link.addEventListener('click', function(e) {
            e.preventDefault();

            const targetId = this.getAttribute('href');
            const targetSection = document.querySelector(targetId);

            if (targetSection) {
                const offsetTop = targetSection.offsetTop - 80; // Offset para navbar fixa

                window.scrollTo({
                    top: offsetTop,
                    behavior: 'smooth'
                });

                // Fechar navbar mobile se estiver aberto
                const navbarCollapse = document.querySelector('.navbar-collapse');
                if (navbarCollapse.classList.contains('show')) {
                    const navbarToggler = document.querySelector('.navbar-toggler');
                    navbarToggler.click();
                }
            }
        });
    });

    // ============================================
    // SCROLL REVEAL ANIMATIONS
    // ============================================

    const observerOptions = {
        threshold: 0.1,
        rootMargin: '0px 0px -50px 0px'
    };

    const observer = new IntersectionObserver(function(entries) {
        entries.forEach(entry => {
            if (entry.isIntersecting) {
                entry.target.classList.add('visible');
            }
        });
    }, observerOptions);

    // Elementos para animação
    const animatedElements = document.querySelectorAll(`
        .hero-content,
        .hero-image,
        .section-title,
        .section-subtitle,
        .service-card,
        .step-item,
        .about-image,
        .about-content,
        .contact-item,
        .stat-item
    `);

    animatedElements.forEach((el, index) => {
        // Adicionar classe de animação baseada no índice
        if (index % 3 === 0) {
            el.classList.add('fade-in');
        } else if (index % 3 === 1) {
            el.classList.add('fade-in-left');
        } else {
            el.classList.add('fade-in-right');
        }

        observer.observe(el);
    });

    // ============================================
    // ANIMAÇÃO DE CONTADOR PARA ESTATÍSTICAS
    // ============================================

    function animateCounter(element, target, duration = 2000) {
        let start = 0;
        const increment = target / (duration / 16);

        const timer = setInterval(() => {
            start += increment;
            if (start >= target) {
                start = target;
                clearInterval(timer);
            }

            // Formatação especial para números
            let displayValue = Math.floor(start);
            if (target >= 1000) {
                displayValue = Math.floor(start).toLocaleString();
            }

            if (element.textContent.includes('+')) {
                element.textContent = displayValue + '+';
            } else if (element.textContent.includes('Anos')) {
                element.textContent = '+' + displayValue + ' Anos';
            } else if (element.textContent.includes('dias')) {
                element.textContent = displayValue + ' dias';
            } else {
                element.textContent = displayValue;
            }
        }, 16);
    }

    // Observer para estatísticas
    const statsObserver = new IntersectionObserver(function(entries) {
        entries.forEach(entry => {
            if (entry.isIntersecting) {
                const statNumber = entry.target.querySelector('.stat-number');
                if (statNumber && !statNumber.classList.contains('animated')) {
                    statNumber.classList.add('animated');

                    // Extrair número do texto
                    const text = statNumber.textContent;
                    let targetNumber = 0;

                    if (text.includes('10')) {
                        targetNumber = 10;
                    } else if (text.includes('5000')) {
                        targetNumber = 5000;
                    } else if (text.includes('15000')) {
                        targetNumber = 15000;
                    } else if (text.includes('90')) {
                        targetNumber = 90;
                    }

                    if (targetNumber > 0) {
                        animateCounter(statNumber, targetNumber);
                    }
                }
                statsObserver.unobserve(entry.target);
            }
        });
    }, { threshold: 0.5 });

    const statItems = document.querySelectorAll('.stat-item');
    statItems.forEach(item => statsObserver.observe(item));

    // ============================================
    // EFEITOS DE HOVER MELHORADOS
    // ============================================

    // Service Cards - Efeito de tilt
    const serviceCards = document.querySelectorAll('.service-card');

    serviceCards.forEach(card => {
        card.addEventListener('mouseenter', function() {
            this.style.transform = 'translateY(-15px) rotateY(5deg)';
        });

        card.addEventListener('mouseleave', function() {
            this.style.transform = 'translateY(0) rotateY(0)';
        });

        // Efeito de movimento com mouse
        card.addEventListener('mousemove', function(e) {
            const rect = this.getBoundingClientRect();
            const x = e.clientX - rect.left;
            const y = e.clientY - rect.top;

            const centerX = rect.width / 2;
            const centerY = rect.height / 2;

            const rotateX = (y - centerY) / 10;
            const rotateY = (centerX - x) / 10;

            this.style.transform = `translateY(-15px) rotateX(${rotateX}deg) rotateY(${rotateY}deg)`;
        });
    });

    // ============================================
    // PARALLAX SUTIL NO HERO
    // ============================================

    //const heroSection = document.getElementById('hero');

    //window.addEventListener('scroll', function() {
    //    const scrolled = window.pageYOffset;
    //    const parallaxSpeed = 0.5;
    //
    //    if (heroSection) {
    //       heroSection.style.transform = `translateY(${scrolled * parallaxSpeed}px)`;
    //    }
    //});

    // ============================================
    // LAZY LOADING PARA IMAGENS
    // ============================================

    if ('IntersectionObserver' in window) {
        const imageObserver = new IntersectionObserver(function(entries, observer) {
            entries.forEach(entry => {
                if (entry.isIntersecting) {
                    const img = entry.target;
                    img.src = img.dataset.src;
                    img.classList.remove('lazy');
                    imageObserver.unobserve(img);
                }
            });
        });

        const lazyImages = document.querySelectorAll('img[data-src]');
        lazyImages.forEach(img => imageObserver.observe(img));
    }

    // ============================================
    // VALIDAÇÃO DE FORMULÁRIO (SE HOUVER)
    // ============================================

    const forms = document.querySelectorAll('form');

    forms.forEach(form => {
        form.addEventListener('submit', function(e) {
            e.preventDefault();

            // Validação básica
            const inputs = form.querySelectorAll('input[required], textarea[required]');
            let isValid = true;

            inputs.forEach(input => {
                if (!input.value.trim()) {
                    isValid = false;
                    input.classList.add('is-invalid');
                } else {
                    input.classList.remove('is-invalid');
                }
            });

            if (isValid) {
                // Simular envio
                showNotification('Mensagem enviada com sucesso!', 'success');
                form.reset();
            } else {
                showNotification('Por favor, preencha todos os campos obrigatórios.', 'error');
            }
        });
    });

    // ============================================
    // SISTEMA DE NOTIFICAÇÕES
    // ============================================

    function showNotification(message, type = 'info') {
        const notification = document.createElement('div');
        notification.className = `alert alert-${type === 'success' ? 'success' : 'danger'} notification`;
        notification.textContent = message;

        notification.style.cssText = `
            position: fixed;
            top: 100px;
            right: 20px;
            z-index: 9999;
            padding: 1rem 1.5rem;
            border-radius: 8px;
            box-shadow: 0 10px 30px rgba(0,0,0,0.3);
            transform: translateX(100%);
            transition: transform 0.3s ease-in-out;
        `;

        document.body.appendChild(notification);

        // Animar entrada
        setTimeout(() => {
            notification.style.transform = 'translateX(0)';
        }, 100);

        // Remover após 5 segundos
        setTimeout(() => {
            notification.style.transform = 'translateX(100%)';
            setTimeout(() => {
                if (notification.parentNode) {
                    notification.parentNode.removeChild(notification);
                }
            }, 300);
        }, 5000);
    }

    // ============================================
    // PRELOADER (OPCIONAL)
    // ============================================

    window.addEventListener('load', function() {
        const preloader = document.getElementById('preloader');
        if (preloader) {
            preloader.style.opacity = '0';
            setTimeout(() => {
                preloader.style.display = 'none';
            }, 500);
        }

        // Trigger inicial das animações
        handleNavbarScroll();
    });

    // ============================================
    // OTIMIZAÇÃO DE PERFORMANCE
    // ============================================

    // Throttle function para scroll events
    function throttle(func, wait) {
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

    // Aplicar throttle nos event listeners de scroll
    const throttledScrollHandler = throttle(() => {
        handleNavbarScroll();
    }, 16);

    window.removeEventListener('scroll', handleNavbarScroll);
    window.addEventListener('scroll', throttledScrollHandler);

    // ============================================
    // ACESSIBILIDADE
    // ============================================

    // Foco em elementos interativos
    const focusableElements = document.querySelectorAll(
        'a, button, input, textarea, select, [tabindex]:not([tabindex="-1"])'
    );

    focusableElements.forEach(element => {
        element.addEventListener('focus', function() {
            this.style.outline = '2px solid var(--cta-green)';
            this.style.outlineOffset = '2px';
        });

        element.addEventListener('blur', function() {
            this.style.outline = 'none';
        });
    });

    // Suporte para navegação por teclado
    document.addEventListener('keydown', function(e) {
        // ESC para fechar modais ou menus
        if (e.key === 'Escape') {
            const navbarCollapse = document.querySelector('.navbar-collapse.show');
            if (navbarCollapse) {
                const navbarToggler = document.querySelector('.navbar-toggler');
                navbarToggler.click();
            }
        }
    });

    // ============================================
    // ANALYTICS E TRACKING (PLACEHOLDER)
    // ============================================

    function trackEvent(category, action, label) {
        // Placeholder para Google Analytics ou similar
        void category;
        void action;
        void label;

        // Exemplo: gtag('event', action, { event_category: category, event_label: label });
    }

    // Track clicks nos botões CTA
    const ctaButtons = document.querySelectorAll('.btn-primary');
    ctaButtons.forEach(button => {
        button.addEventListener('click', function() {
            trackEvent('CTA', 'click', this.textContent.trim());
        });
    });

    // Track navegação
    navLinks.forEach(link => {
        link.addEventListener('click', function() {
            trackEvent('Navigation', 'click', this.getAttribute('href'));
        });
    });

});
