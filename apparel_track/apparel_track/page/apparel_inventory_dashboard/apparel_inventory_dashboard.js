frappe.pages['apparel-inventory-dashboard'].on_page_load = function (wrapper) {
	new ApparelInventoryDashboard(wrapper);
};

class ApparelInventoryDashboard {
	constructor(wrapper) {
		this.page = frappe.ui.make_app_page({
			parent: wrapper,
			title: __('Apparel Inventory Analytics'),
			single_column: true,
		});
		this.page.add_inner_button(__('Refresh'), () => this.load());
		this.page.add_field({
			fieldname: 'days', label: __('Trend Period'), fieldtype: 'Select',
			options: '30\n60\n90', default: '30', change: () => this.load(),
		});
		this.page.add_field({
			fieldname: 'dead_stock_days', label: __('Dead Stock Threshold'), fieldtype: 'Select',
			options: '30\n60\n90\n180', default: '30', change: () => this.load(),
		});
		this.$body = $(wrapper).find('.layout-main-section');
		this.$body.html(this.template());
		this.load();
	}

	template() {
		return `<div class="apparel-dashboard">
			<div class="dashboard-kpis"></div>
			<div class="dashboard-grid">
				<div class="dashboard-panel"><h4>${__('Stock Value by Warehouse')}</h4><div class="stock-value-chart"></div></div>
				<div class="dashboard-panel"><h4>${__('Reorder Triggers Over Time')}</h4><div class="reorder-chart"></div></div>
				<div class="dashboard-panel"><h4>${__('Supplier Reliability')}</h4><div class="supplier-chart"></div></div>
				<div class="dashboard-panel"><h4>${__('Dead Stock Ageing')}</h4><div class="dead-stock-table"></div></div>
			</div>
		</div>`;
	}

	load() {
		const days = this.page.fields_dict.days.get_value() || 30;
		const dead_stock_days = this.page.fields_dict.dead_stock_days.get_value() || 30;
		frappe.call({
			method: 'apparel_track.apparel_track.tasks.get_apparel_dashboard_data',
			args: { days, dead_stock_days },
			freeze: true,
		}).then(({ message }) => this.render(message));
	}

	render(data) {
		this.$body.find('.dashboard-kpis').html([
			this.kpi(__('Stockouts'), data.critical_stockouts, 'red'),
			this.kpi(__('Pending Material Requests'), data.pending_material_requests, 'orange'),
			this.kpi(__('Dead Stock Items'), data.dead_stock_ageing.length, 'blue'),
		].join(''));
		this.chart('.stock-value-chart', __('Stock Value'), data.stock_value_by_warehouse, 'warehouse', 'stock_value', 'bar');
		this.chart('.reorder-chart', __('Auto-Reorder Requests'), data.reorder_triggers, 'transaction_date', 'request_count', 'line');
		this.chart('.supplier-chart', __('Reliability %'), data.supplier_reliability, 'supplier', 'reliability_score', 'bar');
		const rows = data.dead_stock_ageing.map(row => `<tr><td>${frappe.utils.escape_html(row.item_code)}</td><td>${frappe.utils.escape_html(row.warehouse)}</td><td>${row.actual_qty}</td><td>${row.last_movement_date || __('No movement')}</td><td>${row.age_days || '-'}</td></tr>`).join('');
		this.$body.find('.dead-stock-table').html(`<table class="table table-bordered"><thead><tr><th>${__('Item')}</th><th>${__('Warehouse')}</th><th>${__('Qty')}</th><th>${__('Last Movement')}</th><th>${__('Age (Days)')}</th></tr></thead><tbody>${rows || `<tr><td colspan="5" class="text-muted">${__('No dead stock for this threshold')}</td></tr>`}</tbody></table>`);
	}

	kpi(label, value, color) {
		return `<div class="dashboard-kpi"><div class="text-muted">${label}</div><div class="kpi-value text-${color}">${value}</div></div>`;
	}

	chart(selector, title, rows, labelKey, valueKey, type) {
		const labels = rows.map(row => row[labelKey]);
		new frappe.Chart(this.$body.find(selector)[0], {
			type, height: 240, colors: ['#1677ff'], data: { labels, datasets: [{ name: title, values: rows.map(row => Number(row[valueKey] || 0)) }] },
			axisOptions: { xIsSeries: true }, tooltipOptions: { formatTooltipX: value => value, formatTooltipY: value => value },
		});
	}
}