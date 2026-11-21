/** @typedef {{id:number, title:string, payload:object, author:string, voided_at:string|null}} BusinessCase */
/** @typedef {{id:number, case_id:number, status:'queued'|'running'|'complete'|'failed'}} Run */
/** @typedef {{id:number, run_id:number, digest:string, report:{summary:string, metrics:object, sections:Array}}} Evidence */
/** @typedef {{id:number, case_id:number, payload:Array, digest:string, created_at:string}} PurchaseOrder */
/** @typedef {{ingredient:string, on_hand:string, occupied:string, available:string, holders:Array}} WarehouseRow */
