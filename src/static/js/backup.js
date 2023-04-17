function AddBackup() {
  fetch("/settings/backups/add", {method: "POST"})
    .then(response => {
      if (!response.ok) 
        response.text().then(text => OpenErrorModal(text, response.status));
      else 
        window.location=window.location;
    }) 
    .catch(error => OpenErrorModal(error, 500));
}

function DeleteBackup(backup) {
  fetch("/settings/backups/delete/"+backup, {method: "POST"})
    .then(response => {
      if (!response.ok) 
        response.text().then(text => OpenErrorModal(text, response.status));
      else 
        window.location=window.location;
    }) 
    .catch(error => OpenErrorModal(error, 500));
}

function LoadBackup(backup) {
  fetch("/settings/backups/load/"+backup, {method: "POST"})
    .then(response => {
      if (!response.ok) 
        response.text().then(text => OpenErrorModal(text, response.status));
      else 
        window.location=window.location;
    }) 
    .catch(error => OpenErrorModal(error, 500));
}

function DownloadBackup(backup) {
  var req = new XMLHttpRequest();
  req.open("POST", "/settings/backups/download/"+backup, true);
  req.responseType = "blob";
  req.setRequestHeader("Content-type", "application/x-www-form-urlencoded");
  req.onreadystatechange = function() {
    if (this.readyState == 4 && this.status == 200) {
      var blob = new Blob([this.response], {"type": "application/db"});
      var url = window.URL.createObjectURL(blob);
      var link = document.createElement('a');
      document.body.appendChild(link);
      link.style = "display: none";
      link.href = url;
      link.download = backup;
      link.click();
      setTimeout(() => {
        window.URL.revokeObjectURL(url);
        link.remove(); 
      } , 100);
    }
    else if (this.readyState === 4 && this.status != 400 ) {
      var blob = new Blob([this.response], {type: "text"});
      var reader = new FileReader();
      reader.onload = function() {
        OpenErrorModal(reader.result, this.status);
      }
      reader.readAsText(blob);
    }
  };
  req.send();
}
