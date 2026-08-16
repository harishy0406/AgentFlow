"""
Phase 6: Evaluation Test Corpus

Contains 15 diverse project briefs used for automated benchmarking
across the Single-LLM, Multi-Agent (No-Graph), and AgentFlow configurations.
"""

EVAL_CORPUS = [
    {
        "name": "E-Commerce Platform",
        "brief": "A B2C e-commerce platform supporting product catalog, user cart, secure checkout via Stripe, and order tracking. Needs admin dashboard for inventory management.",
        "domain": "Retail"
    },
    {
        "name": "Healthcare Appointment System",
        "brief": "A patient portal for booking appointments, viewing medical history, and teleconsultation. Must comply with HIPAA and support doctor availability scheduling.",
        "domain": "Healthcare"
    },
    {
        "name": "Fintech Wallet App",
        "brief": "A mobile-first digital wallet that allows peer-to-peer transfers, bill payments, and crypto purchasing. Requires strong encryption and KYC onboarding.",
        "domain": "Finance"
    },
    {
        "name": "Social Media Feed",
        "brief": "A microblogging platform with real-time feeds, user followers, media uploads (images/videos), and liking/commenting features.",
        "domain": "Social"
    },
    {
        "name": "IoT Home Automation",
        "brief": "A central hub to manage smart home devices (lights, thermostats, locks). Must support real-time MQTT telemetry and user-defined automation routines.",
        "domain": "IoT"
    },
    {
        "name": "Online Learning Management",
        "brief": "An LMS for schools offering video courses, quizzes, assignments, and a grading system. Needs roles for students, teachers, and admins.",
        "domain": "Education"
    },
    {
        "name": "Food Delivery Service",
        "brief": "A three-sided marketplace for customers, restaurants, and delivery drivers. Includes real-time GPS tracking and live order status updates.",
        "domain": "Logistics"
    },
    {
        "name": "Inventory Management API",
        "brief": "A headless REST API for warehouse operations, handling stock intake, dispatch, barcode scanning integration, and low-stock alerts.",
        "domain": "Enterprise"
    },
    {
        "name": "Travel Booking Aggregator",
        "brief": "A flight and hotel booking engine that aggregates data from external APIs. Requires complex search filters, pricing caching, and user itineraries.",
        "domain": "Travel"
    },
    {
        "name": "Fitness Tracking App",
        "brief": "A fitness app that records daily workouts, tracks macros, and syncs with Apple Health/Google Fit. Includes social leaderboards.",
        "domain": "Health & Fitness"
    },
    {
        "name": "Real Estate Listings",
        "brief": "A property marketplace with map-based search, virtual tours, and a messaging system between buyers and agents.",
        "domain": "Real Estate"
    },
    {
        "name": "Event Ticketing Platform",
        "brief": "A high-concurrency ticket sales system for concerts and sports. Needs queue management, QR code ticket generation, and seating charts.",
        "domain": "Entertainment"
    },
    {
        "name": "SaaS Subscription Billing",
        "brief": "A microservice for managing B2B SaaS subscriptions, handling tier upgrades/downgrades, invoice generation, and dunning workflows.",
        "domain": "SaaS"
    },
    {
        "name": "AI Content Generator",
        "brief": "A web app that allows marketing teams to generate blog posts, ad copy, and social media captions using an LLM backend. Needs prompt templating.",
        "domain": "AI/Productivity"
    },
    {
        "name": "Fleet Tracking Dashboard",
        "brief": "A commercial fleet management tool to monitor vehicle health, fuel consumption, driver behavior, and route optimization.",
        "domain": "Logistics"
    }
]
