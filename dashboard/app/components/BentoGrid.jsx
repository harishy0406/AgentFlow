import React from "react";

/**
 * Enhanced Bento Grid Component - Modern, responsive grid system
 * with advanced layout capabilities for SaaS interfaces
 */

export function BentoGrid({ children, columns = 12, gap = 16, className = "" }) {
  return (
    <div
      className={`bento-grid-enhanced ${className}`}
      style={{
        display: "grid",
        gridTemplateColumns: `repeat(${columns}, 1fr)`,
        gap: `${gap}px`,
        marginTop: "24px"
      }}
    >
      {children}
    </div>
  );
}

/**
 * Individual Bento Card with enhanced styling options
 */
export function BentoCard({
  children,
  span = 4,
  accentColor = "var(--neon-green)",
  hoverEffect = true,
  className = "",
  onClick,
  gradient = false
}) {
  const cardStyle = {
    gridColumn: `span ${span}`,
    background: "var(--bg-card)",
    border: gradient ? "none" : "1px solid var(--border)",
    borderRadius: "16px",
    padding: "24px",
    position: "relative",
    overflow: "hidden",
    transition: "all 0.3s cubic-bezier(0.4, 0, 0.2, 1)",
    ...(gradient && {
      background: `linear-gradient(135deg, ${accentColor}15 0%, transparent 100%)`,
      border: "1px solid"
    }),
    ...(hoverEffect && {
      cursor: onClick ? "pointer" : "default"
    })
  };

  const hoverStyle = hoverEffect ? {
    borderColor: onClick ? accentColor : "var(--border-hover)",
    transform: "translateY(-2px)",
    boxShadow: onClick ? `0 8px 24px ${accentColor}20` : "var(--shadow-glow)"
  } : {};

  return (
    <div
      className={`bento-card-enhanced ${className}`}
      style={cardStyle}
      onClick={onClick}
      data-hover-style={JSON.stringify(hoverStyle)}
    >
      {children}
    </div>
  );
}

/**
 * Bento Header with accent bar
 */
export function BentoHeader({ badge, title, description, accentColor = "var(--neon-green)" }) {
  return (
    <div className="bento-header">
      {badge && (
        <span
          className="bento-badge"
          style={{
            backgroundColor: accentColor,
            color: "var(--bg-primary)",
            fontSize: "11px",
            fontWeight: "700",
            padding: "4px 10px",
            borderRadius: "6px",
            marginBottom: "12px",
            display: "inline-block"
          }}
        >
          {badge}
        </span>
      )}
      <h3 style={{
        fontSize: "18px",
        fontWeight: "700",
        marginBottom: "8px",
        lineHeight: "1.4"
      }}>
        {title}
      </h3>
      {description && (
        <p style={{
          color: "var(--text-secondary)",
          fontSize: "14px",
          lineHeight: "1.6",
          marginBottom: "16px"
        }}>
          {description}
        </p>
      )}
    </div>
  );
}

/**
 * Modern Feature Card for products/features
 */
export function FeatureCard({ icon, title, description, features, accentColor = "var(--neon-green)" }) {
  return (
    <BentoCard span={4} accentColor={accentColor} hoverEffect={true}>
      <div className="bento-content">
        {icon && <div className="feature-icon">{icon}</div>}
        <BentoHeader title={title} description={description} accentColor={accentColor} />
        {features && (
          <ul className="feature-list">
            {features.map((feature, index) => (
              <li key={index} className="feature-item">
                <span className="feature-check">✓</span>
                <span className="feature-text">{feature}</span>
              </li>
            ))}
          </ul>
        )}
      </div>
      <style jsx>{`
        .bento-content {
          display: flex;
          flex-direction: column;
          height: 100%;
        }
        .feature-icon {
          margin-bottom: 16px;
          font-size: 24px;
          color: ${accentColor};
        }
        .feature-list {
          list-style: none;
          padding: 0;
          margin: 12px 0 0 0;
          flex-grow: 1;
        }
        .feature-item {
          display: flex;
          align-items: flex-start;
          margin-bottom: 8px;
          font-size: 13px;
        }
        .feature-check {
          margin-right: 8px;
          color: ${accentColor};
          min-width: 16px;
        }
        .feature-text {
          color: var(--text-primary);
        }
      `}</style>
    </BentoCard>
  );
}

/**
 * Pricing Card Component
 */
export function PricingCard({
  title,
  price,
  period,
  description,
  features,
  accentColor = "var(--neon-green)",
  buttonText,
  onButtonClick,
  popular = false
}) {
  return (
    <BentoCard
      span={4}
      accentColor={popular ? "var(--accent-yellow)" : accentColor}
      gradient={true}
      className={popular ? "pricing-popular" : ""}
    >
      <div className="pricing-content">
        {popular && (
          <div className="popular-badge">MOST POPULAR</div>
        )}
        <BentoHeader title={title} description={description} accentColor={popular ? "var(--accent-yellow)" : accentColor} />

        <div className="price-display">
          <span className="price-amount">{price}</span>
          <span className="price-period">{period}</span>
        </div>

        {features && (
          <ul className="pricing-features">
            {features.map((feature, index) => (
              <li key={index} className="pricing-feature-item">
                <span className="pricing-feature-check">✓</span>
                <span className="pricing-feature-text">{feature}</span>
              </li>
            ))}
          </ul>
        )}

        <button
          className={`pricing-button ${popular ? "popular-button" : ""}`}
          onClick={onButtonClick}
        >
          {buttonText}
        </button>
      </div>

      <style jsx>{`
        .pricing-content {
          position: relative;
          height: 100%;
          display: flex;
          flex-direction: column;
        }
        .popular-badge {
          background: var(--accent-yellow);
          color: var(--bg-primary);
          font-size: 11px;
          font-weight: 700;
          padding: 4px 10px;
          border-radius: 6px;
          text-transform: uppercase;
          letter-spacing: 0.5px;
          align-self: flex-start;
          margin-bottom: 12px;
        }
        .price-display {
          margin: 16px 0;
          display: flex;
          align-items: baseline;
          gap: 8px;
        }
        .price-amount {
          font-size: 36px;
          font-weight: 900;
          font-family: var(--font-display);
          color: var(--text-primary);
        }
        .price-period {
          font-size: 14px;
          color: var(--text-secondary);
          font-weight: 500;
        }
        .pricing-features {
          list-style: none;
          padding: 0;
          margin: 16px 0;
          flex-grow: 1;
        }
        .pricing-feature-item {
          display: flex;
          align-items: flex-start;
          margin-bottom: 8px;
          font-size: 13px;
        }
        .pricing-feature-check {
          margin-right: 8px;
          color: ${accentColor};
          min-width: 16px;
        }
        .pricing-feature-text {
          color: var(--text-primary);
        }
        .pricing-button {
          margin-top: 16px;
          width: 100%;
          padding: 12px;
          border-radius: 8px;
          font-weight: 700;
          font-size: 14px;
          transition: all 0.2s ease;
          cursor: pointer;
          border: none;
        }
        .popular-button {
          background: var(--accent-yellow);
          color: var(--bg-primary);
        }
        .popular-button:hover {
          background: var(--accent-yellow);
          opacity: 0.9;
        }
      `}</style>
    </BentoCard>
  );
}

// Add hover effects with JavaScript
export function addBentoHoverEffects() {
  if (typeof window !== "undefined") {
    const cards = document.querySelectorAll(".bento-card-enhanced");
    cards.forEach(card => {
      const hoverStyle = card.getAttribute("data-hover-style");
      if (hoverStyle) {
        const styleObj = JSON.parse(hoverStyle);

        card.addEventListener("mouseenter", () => {
          Object.assign(card.style, styleObj);
        });

        card.addEventListener("mouseleave", () => {
          card.style.borderColor = "var(--border)";
          card.style.transform = "none";
          card.style.boxShadow = "none";
        });
      }
    });
  }
}