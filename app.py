"""
Med Spa Accounting Pipeline — Streamlit Application
Run with: streamlit run app.py
"""
import streamlit as st

st.set_page_config(
    page_title="Med Spa Pipeline",
    page_icon="\U0001f489",
    layout="wide",
)

st.title("Med Spa Accounting Pipeline")

tab1, tab2, tab3, tab4 = st.tabs([
    "\U0001f4e5 Pipeline Processing",
    "\U0001f4e6 Inventory Setup",
    "\U0001f4b3 Vendor Payments",
    "\U0001f4ca Analytics",
])

with tab1:
    from ui.pipeline_tab import render_pipeline_tab
    render_pipeline_tab()

with tab2:
    from ui.inventory_tab import render_inventory_tab
    render_inventory_tab()

with tab3:
    from ui.vendor_tab import render_vendor_tab
    render_vendor_tab()

with tab4:
    from ui.analytics_tab import render_analytics_tab
    render_analytics_tab()
