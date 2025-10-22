window.onload = function() {
  for (var form of document.forms) {
    if (!form.id.includes('newAnnouncementForm') && !form.id.includes('newYTAnnouncementForm')){
      console.log("clearing" + form.id)
      form.reset()
    }
  }
}

function cancelEdit(button) {
  const guildID = button.dataset.guild;
  const addForm = document.getElementById(guildID+'-newAnnouncementForm');
  var buttonContainer = addForm.querySelector('.buttonContainer');
  var submitButton = addForm.querySelector('input[type="submit"]')
  var hiddenAnnouncementID = addForm.querySelector('input[name="announcementID"]')

  addForm.action = "/discord/announcement/add"
  addForm.querySelector('summary').innerHTML = "Add Twitch Announcement";
  addForm.querySelector('.streamName').value = '';
  addForm.querySelector('.channel').options.selectedIndex = 0;
  addForm.querySelector('.announcementText').value = '';
  submitButton.value = "Add Announcement";
  addForm.querySelector('details').appendChild(submitButton)

  hiddenAnnouncementID.remove()
  buttonContainer.remove()

  addForm.querySelector('details').removeAttribute('open');
}

function editAnnouncement(button) {
  const announcementID = button.dataset.announcement;
  const guildID = button.dataset.guild;
  const channelID = button.dataset.channel;
  console.log(guildID)

  const announcementForm = document.getElementById(announcementID+'-manageAnnouncementForm');
  const addForm = document.getElementById(guildID+'-newAnnouncementForm');
  const formTest = addForm.querySelector('input[name="announcementID"]')
  console.log(formTest)

  if (formTest) {
    if (formTest.value === announcementID) {
      return;
    } else {
      var hiddenAnnouncementID = addForm.querySelector('input[name="announcementID"]')
      var buttonContainer = addForm.querySelector('.buttonContainer');
      var cancelButton = buttonContainer.querySelector('button[type="button"]')
    }
  } else {
    var hiddenAnnouncementID = document.createElement("input");
    var buttonContainer = document.createElement("div");
    var cancelButton = document.createElement("button");
  }

  const streamName = announcementForm.querySelector('legend').innerText.replace(":", "");
  let announcementText = announcementForm.querySelector('span').innerText.split('\n')[0];
  announcementText = announcementText.split(': ')[1]

  addForm.action = "/discord/announcement/edit"
  addForm.querySelector('summary').innerHTML = "Edit Twitch Announcement";
  addForm.querySelector('.streamName').value = streamName;
  addForm.querySelector('.channel').value = channelID;
  addForm.querySelector('.announcementText').value = announcementText;
  addForm.querySelector('input[type="submit"]').value = "Edit Announcement";

  hiddenAnnouncementID.type = "hidden";
  hiddenAnnouncementID.name = "announcementID";
  hiddenAnnouncementID.value = announcementID;
  addForm.querySelector('details').appendChild(hiddenAnnouncementID)
  
  buttonContainer.className = "buttonContainer";
  addForm.querySelector('details').appendChild(buttonContainer)
  buttonContainer.appendChild(addForm.querySelector('input[type="submit"]'));
  
  cancelButton.type = "button"
  cancelButton.value = "Cancel"
  cancelButton.innerText = "Cancel"
  cancelButton.dataset.guild = guildID
  cancelButton.onclick = function() {cancelEdit(cancelButton);}
  buttonContainer.appendChild(cancelButton)

  addForm.querySelector('details').setAttribute('open', '');
}

function cancelYTEdit(button) {
  const guildID = button.dataset.guild;
  const addForm = document.getElementById(guildID+'-newYTAnnouncementForm');
  var buttonContainer = addForm.querySelector('.buttonContainer');
  var submitButton = addForm.querySelector('input[type="submit"]')
  var hiddenAnnouncementID = addForm.querySelector('input[name="announcementID"]')

  addForm.action = "/discord/ytannouncement/add"
  addForm.querySelector('summary').innerHTML = "Add Youtube Announcement";
  addForm.querySelector('.ytChannelID').value = '';
  addForm.querySelector('.channel').options.selectedIndex = 0;
  addForm.querySelector('.announcementText').value = '';
  submitButton.value = "Add Announcement";
  addForm.querySelector('details').appendChild(submitButton)

  hiddenAnnouncementID.remove()
  buttonContainer.remove()

  addForm.querySelector('details').removeAttribute('open');
}

function editYTAnnouncement(button) {
  const announcementID = button.dataset.announcement;
  const guildID = button.dataset.guild;
  const channelID = button.dataset.channel;
  console.log(guildID)

  const announcementForm = document.getElementById(announcementID+'-manageYTAnnouncementForm');
  const addForm = document.getElementById(guildID+'-newYTAnnouncementForm');
  const formTest = addForm.querySelector('input[name="announcementID"]')
  console.log(formTest)

  if (formTest) {
    if (formTest.value === announcementID) {
      return;
    } else {
      var hiddenAnnouncementID = addForm.querySelector('input[name="announcementID"]')
      var buttonContainer = addForm.querySelector('.buttonContainer');
      var cancelButton = buttonContainer.querySelector('button[type="button"]')
    }
  } else {
    var hiddenAnnouncementID = document.createElement("input");
    var buttonContainer = document.createElement("div");
    var cancelButton = document.createElement("button");
  }

  const ytChannelID = announcementForm.querySelector('legend').innerText.replace(":", "");
  let announcementText = announcementForm.querySelector('span').innerText.split('\n')[0];
  announcementText = announcementText.split(': ')[1]

  addForm.action = "/discord/ytannouncement/edit"
  addForm.querySelector('summary').innerHTML = "Edit Youtube Announcement";
  addForm.querySelector('.ytChannelID').value = ytChannelID;
  addForm.querySelector('.channel').value = channelID;
  addForm.querySelector('.announcementText').value = announcementText;
  addForm.querySelector('input[type="submit"]').value = "Edit Announcement";

  hiddenAnnouncementID.type = "hidden";
  hiddenAnnouncementID.name = "announcementID";
  hiddenAnnouncementID.value = announcementID;
  addForm.querySelector('details').appendChild(hiddenAnnouncementID)
  
  buttonContainer.className = "buttonContainer";
  addForm.querySelector('details').appendChild(buttonContainer)
  buttonContainer.appendChild(addForm.querySelector('input[type="submit"]'));
  
  cancelButton.type = "button"
  cancelButton.value = "Cancel"
  cancelButton.innerText = "Cancel"
  cancelButton.dataset.guild = guildID
  cancelButton.onclick = function() {cancelYTEdit(cancelButton);}
  buttonContainer.appendChild(cancelButton)

  addForm.querySelector('details').setAttribute('open', '');
}