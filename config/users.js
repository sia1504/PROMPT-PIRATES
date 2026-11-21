// Demo users for the Stock Desk page. DEMO GATE ONLY: no passwords, made-up emails on the
// reserved domain manyavar.example. Anyone can read this file, so it is not security.
// scope: 'all' | {stores:[...]} | {source:'WH-KOL'}
window.ROLES = {
  merchandiser:  {label:'Merchandiser', can:['decide','export_csv','export_pick','export_json'], tabs:['queue','rescue','ghost','ageing','brief','details']},
  head:          {label:'Head of supply chain', can:['export_csv','export_pick','export_json'], tabs:['queue','rescue','ghost','ageing','brief','details']},
  area_manager:  {label:'Area manager', can:['decide_scoped','export_csv'], tabs:['queue','rescue','ageing','brief']},
  warehouse:     {label:'Warehouse lead', can:['pick','dispatch','export_pick'], tabs:['queue','brief']},
  store_manager: {label:'Store manager', can:['receive'], tabs:['brief','queue']}
};
window.USERS = [
  {email:'priya.merch@manyavar.example', name:'Priya Merchant', role:'merchandiser', scope:'all'},
  {email:'head.supply@manyavar.example', name:'Hemant Supply', role:'head', scope:'all'},
  {email:'wh.kolkata@manyavar.example', name:'Wasim Kolkata', role:'warehouse', scope:{source:'WH-KOL'}},
  {email:'rakesh.srivastava@manyavar.example', area_manager_id:'AM-01', name:'Rakesh Srivastava', role:'area_manager', scope:{stores:['LKO-01','LKO-02','LKO-03','LKO-04']}},
  {email:'alok.tiwari@manyavar.example', area_manager_id:'AM-02', name:'Alok Tiwari', role:'area_manager', scope:{stores:['KNP-01','KNP-02','KNP-03']}},
  {email:'nitin.sinha@manyavar.example', area_manager_id:'AM-03', name:'Nitin Sinha', role:'area_manager', scope:{stores:['PAT-01','PAT-02','PAT-03','PAT-04']}},
  {email:'pankaj.jha@manyavar.example', area_manager_id:'AM-04', name:'Pankaj Jha', role:'area_manager', scope:{stores:['MZF-01','MZF-02']}},
  {email:'harish.gowda@manyavar.example', area_manager_id:'AM-05', name:'Harish Gowda', role:'area_manager', scope:{stores:['BLR-01','BLR-02','BLR-03','BLR-04','BLR-05']}},
  {email:'mahesh.shetty@manyavar.example', area_manager_id:'AM-06', name:'Mahesh Shetty', role:'area_manager', scope:{stores:['MYS-01','MYS-02']}},
  {email:'lko01.store@manyavar.example', name:'Test Manager LKO-01', role:'store_manager', scope:{stores:['LKO-01']}},
  {email:'pat01.store@manyavar.example', name:'Test Manager PAT-01', role:'store_manager', scope:{stores:['PAT-01']}},
  {email:'mzf01.store@manyavar.example', name:'Test Manager MZF-01', role:'store_manager', scope:{stores:['MZF-01']}},
  {email:'blr05.store@manyavar.example', name:'Test Manager BLR-05', role:'store_manager', scope:{stores:['BLR-05']}}
];
