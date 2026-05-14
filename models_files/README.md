# Bu klasor model dosyalari icindir.
# 
# Railway'e deploy ettikten SONRA, asagidaki model dosyalarini bu klasore yukleyin:
#
# - best.pt           (~23 MB)  - PFN keypoint detection modeli
# - femur_model.pt    (~?? MB)  - AO siniflama modeli
#
# GitHub'a model dosyalari yuklenmiyor (.gitignore tarafindan engelleniyor).
# Bu sayede repo boyutu kuçuk kalir ve modeller ayri yuklenebilir.
#
# Railway'e yukleme yontemleri:
#   1. Railway dashboard -> Volumes -> Upload files
#   2. Railway CLI:  railway run cp local_path/best.pt /app/models_files/
#   3. Git ile (eger model boyutu kucukse): .gitignore'dan *.pt cikarip push
