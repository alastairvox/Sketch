async function testClick() {
    const response = await fetch('/test')
    // do whatever you want with your response
    const button = document.querySelector('button');
    button.innerHTML = await response.text();
  }