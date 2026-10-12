DASHBOARD_QSS = """
    QWidget#dashboardPage, QWidget#dashboardContent, QScrollArea {
        background: #F0F5FF; border: none;
    }
    QFrame#dashboardCard {
        background: white; border: 1px solid #E0E8F4; border-radius: 14px;
    }
    QLabel { background: transparent; border: none; color: #64748B; font-size: 13px; }
    QLabel#pageTitle { color: #0F172A; font-size: 28px; font-weight: 700; }
    QLabel#sectionTitle { color: #1E293B; font-size: 15px; font-weight: 600; }
    QLabel#metricValue { color: #0E2971; font-size: 32px; font-weight: 700; }
    QLabel#categoryName { color: #334155; font-weight: 600; }
    QLabel#emptyState { padding: 18px 0; }
    QPushButton {
        background: #EFF6FF; color: #2563EB; border: 1px solid #DBEAFE;
        border-radius: 9px; padding: 10px 14px; font-size: 13px; font-weight: 600;
    }
    QPushButton:hover { background: #DBEAFE; border-color: #93C5FD; }
    QPushButton:focus { border: 2px solid #2563EB; }
    QPushButton#primaryAction { background: #2563EB; border-color: #2563EB; color: white; }
    QPushButton#primaryAction:hover { background: #1D4ED8; }
    QPushButton#stockAlert { text-align: left; background: #FFFBEB; color: #92400E; border-color: #FDE68A; }
    QPushButton#stockAlert[critical="true"] { background: #FFF1F2; color: #9F1239; border-color: #FECDD3; }
    QPushButton#stockAlert:hover { border-color: #2563EB; }
    QProgressBar { background: #E8EFFA; border: none; border-radius: 4px; }
    QProgressBar::chunk { background: #3482FF; border-radius: 4px; }
"""
